# Sadhana Backend — Infrastructure

One Terraform root module (no `core`/`edge` split — that split exists in the
sibling community-events project because several app repos share one load
balancer/Cloud Armor policy/DNS zone; here there's a single API and nothing
else to share those with).

## Resources

- A custom VPC + subnet — used for the LB's NEG to reach the backend VM, and
  for IAP's SSH/tunnel path to it.
- A single `google_compute_instance` (no external IP) running both
  Elasticsearch and search-api in Docker, talking to each other over
  localhost, with a separate persistent disk for ES's data. search-api used
  to run on Cloud Run; it moved onto this VM to cut Cloud Run's cold-start
  latency out of the request path and to avoid running two billed compute
  resources when one was already sitting there under-used. The trade-off is
  availability: a problem with this one VM now takes down search along with
  it, where Cloud Run being down and the ES VM being down used to be
  independent failures.
- Firewall rules: Google's LB/health-check ranges → the VM's `:8080`
  (search-api) — this, not a rule on `:9200`, is what keeps Elasticsearch
  off the internet, since nothing external needs to reach it anymore — plus
  IAP's fixed range → `:22`, used both for the manual index-setup step below
  and for every deploy's SSH-based redeploy (see `scripts/redeploy-api.sh`).
- A Load Balancer (reserved IP, a `GCE_VM_IP_PORT` NEG + health check
  pointing at the VM's `:8080`, backend service, URL map, HTTPS proxy,
  forwarding rule, HTTP→HTTPS redirect) — partly to give Cloud Armor
  something to attach to (it can't attach to a bare VM), partly to terminate
  real TLS. No purchased domain or Cloud DNS zone: the managed cert covers
  `<ip-with-dashes>.sslip.io`, a free wildcard DNS service that resolves to
  the literal IP with zero registration — Google's cert validation only
  checks DNS resolution, not ownership, so this is satisfied without owning
  anything. See `local.public_domain` in `lb.tf`.
- `google_compute_security_policy` (Cloud Armor) — per-IP throttle.
- Artifact Registry repo, the ES VM's + deployer's service accounts, Secret
  Manager secret *resources* (values set by hand, never through Terraform).

## First-time bootstrap (manual, one-time — run these yourself)

### 1. Terraform state bucket

```bash
PROJECT_ID=<your-project-id>
REGION=<your-region>

gcloud storage buckets create gs://${PROJECT_ID}-tfstate \
  --project=${PROJECT_ID} --location=${REGION} --uniform-bucket-level-access
gcloud storage buckets update gs://${PROJECT_ID}-tfstate --versioning
```

### 2. Workload Identity Federation

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

gcloud iam workload-identity-pools create github-pool \
  --project=$PROJECT_ID --location=global --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project=$PROJECT_ID --location=global --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository_owner == '<your-github-username>'"

gcloud iam service-accounts create sadhana-backend-deployer --project=$PROJECT_ID \
  --display-name="sadhana-backend-deployer (GitHub Actions deploy)"

gcloud iam service-accounts add-iam-policy-binding \
  "sadhana-backend-deployer@${PROJECT_ID}.iam.gserviceaccount.com" --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/<your-github-username>/sadhana-backend"
```

Keep this step permanently manual — never let Terraform manage its own trust
root.

### 3. First apply — secret resource only

Run locally with your own `gcloud` user credentials (Owner/Editor on the
project) — not the deploy SA, which doesn't exist with the right IAM until
a later apply creates it. Targeted deliberately: the ES VM's startup script
reads `es-elastic-password` on first boot, so the *secret resource* must
exist (via Terraform, so it isn't fighting Terraform for ownership later)
and have a *value* (via the next step, by hand) before the VM itself is
created — doing the full apply in one shot would boot the VM before a human
had a chance to populate the password.

```bash
cd infra/terraform
terraform init -backend-config="bucket=${PROJECT_ID}-tfstate" -backend-config="prefix=backend"
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}" \
  -target=google_secret_manager_secret.es_elastic_password
```

### 4. Populate the bootstrap password, then the full apply

```bash
openssl rand -base64 24 | gcloud secrets versions add es-elastic-password --data-file=- --project=$PROJECT_ID

terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}"
```

The VM comes up here and, a minute or two later, `es-startup.sh` mints
`es-api-key` on its own (ES needs to finish coming up and get cache-warmed
first — see the script) — no manual "SSH in and mint a key" step anymore.
`search-api` itself still doesn't start yet, though: nothing's been pushed
to Artifact Registry until the first push to `dev`, which is what actually
runs it (via `scripts/redeploy-api.sh` over SSH). The managed SSL cert also
starts as `PROVISIONING` here — poll with
`gcloud compute ssl-certificates describe sadhana-ssl-cert --format="value(managed.status)"`
until it reaches `ACTIVE` (sslip.io resolves instantly, so this is typically
well under an hour, not the up-to-24h a real registrar can take).

### 5. Set up the index

The ES VM has no external IP, so tunnel in via IAP (your own gcloud user
needs `roles/iap.tunnelResourceAccessor` on the project for this):

```bash
gcloud compute ssh sadhana-elasticsearch --zone=<your-zone> --tunnel-through-iap -- \
  -L 9200:localhost:9200 -N &

uv run python -m ingest.run \
  --content-dir content/shlokas \
  --es-host http://localhost:9200 \
  --es-user elastic \
  --es-password "$(gcloud secrets versions access latest --secret=es-elastic-password)"
```

Use the `elastic` superuser (`es-elastic-password`), not `es-api-key` — that
key is minted read-only on `shlokas` (see `es-startup.sh`), on purpose,
since it's what the running `search-api` service uses to *query* ES. It
doesn't have `create_index`/write privileges, so `ingest/run.py` can't use
it — that's what `--es-user`/`--es-password` are for.

If the command above fails because `es-elastic-password` has no version
yet, that's a different, earlier step — see step 4.

Re-running ingestion later (a corpus update, say) uses this same command —
`index_entries()` upserts by each entry's own slug, so it's safe to run
again without duplicating anything. To fully replace the corpus instead
(e.g. after deleting entries, not just editing them), delete the index
first: `curl -X DELETE http://localhost:9200/shlokas -u elastic:<password>`.

### 6. Set GitHub Actions repo variables

Under **Settings → Secrets and variables → Actions → Variables** in the
`sadhana-backend` repo:

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | your project ID |
| `GCP_REGION` | `us-east1` |
| `GCP_ZONE` | `us-east1-b` |
| `WORKLOAD_IDENTITY_PROVIDER` | `projects/<number>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |

### 7. Push to `dev`

The deploy job builds+pushes the image, re-applies Terraform, then SSHes
into the VM (via IAP, same path as step 5) to run `scripts/redeploy-api.sh`
with the new image tag — that's what actually gets the new code serving.

## After bootstrap

Every subsequent push to `dev` redeploys automatically. `main` never
redeploys — single-environment setup, `dev` is what's live.

## Risks / operating notes

- **Cost**: the backend VM and the LB's forwarding rules are the two fixed
  monthly costs regardless of traffic — there's no Cloud Run component left
  to scale to zero.
- **Deploys have a downtime window**: `redeploy-api.sh` removes the running
  `search-api` container before starting the new one (an existing container
  is pinned to its original image, so picking up a new tag means recreating
  it) — a few seconds of failed requests on every push to `dev`, not just on
  incidents.
- **sslip.io is a third-party free service, not a Google product** — if it
  ever disappeared, the managed cert would stop renewing (certs auto-renew
  only while the domain keeps resolving correctly). Low risk for a widely-used
  service, but worth knowing; swapping to a real purchased domain later is a
  one-line change to `local.public_domain` in `lb.tf`.
- **Single-node ES has no HA, and search-api now shares its fate** —
  deliberate, matches the plan's chosen hosting approach for this scale; a
  VM failure takes the whole API down, not just search quality, until the
  index is re-ingested (cheap — the catalog is small and `ingest/run.py` is
  idempotent) or the persistent disk is reattached to a replacement VM.
