# Sadhana Backend — Infrastructure

One Terraform root module (no `core`/`edge` split — that split exists in the
sibling community-events project because several app repos share one load
balancer/Cloud Armor policy/DNS zone; here there's a single API and nothing
else to share those with).

## Resources

- A custom VPC + subnet, used for exactly one thing: Cloud Run's Direct VPC
  egress path to Elasticsearch.
- A single `google_compute_instance` (no external IP) running Elasticsearch
  in Docker, with a separate persistent disk for its data.
- Firewall rules: Cloud Run's subnet → the ES VM's `:9200` (and nothing
  else — this is what actually keeps Elasticsearch off the internet), plus
  IAP's fixed range → `:22` for the one manual SSH step below.
- `sadhana-search-api`, a Cloud Run v2 service reaching ES over the VPC,
  `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`-only (bypassing the LB by hitting
  its own `*.run.app` URL is blocked, not just discouraged).
- A Load Balancer (reserved IP, serverless NEG, backend service, URL map,
  HTTPS proxy, forwarding rule, HTTP→HTTPS redirect) — partly to give Cloud
  Armor something to attach to (it can't attach to a bare Cloud Run URL),
  partly to terminate real TLS. No purchased domain or Cloud DNS zone: the
  managed cert covers `<ip-with-dashes>.sslip.io`, a free wildcard DNS
  service that resolves to the literal IP with zero registration — Google's
  cert validation only checks DNS resolution, not ownership, so this is
  satisfied without owning anything. See `local.public_domain` in `lb.tf`.
- `google_compute_security_policy` (Cloud Armor) — per-IP throttle.
- Artifact Registry repo, runtime + deployer service accounts, Secret
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
terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -var="image_tag=bootstrap" \
  -target=google_secret_manager_secret.es_elastic_password
```

### 4. Populate the bootstrap password, then the full apply

```bash
openssl rand -base64 24 | gcloud secrets versions add es-elastic-password --data-file=- --project=$PROJECT_ID

terraform apply -var="project_id=${PROJECT_ID}" -var="region=${REGION}" -var="image_tag=bootstrap"
```

`image_tag=bootstrap` is a placeholder — nothing has been pushed to Artifact
Registry yet, so `sadhana-search-api`'s first revision will fail to start.
That's fine; the real image (and a working `es-api-key`, from the next step)
land before anything actually needs to serve traffic. The managed SSL cert
also starts as `PROVISIONING` here — poll with
`gcloud compute ssl-certificates describe sadhana-ssl-cert --format="value(managed.status)"`
until it reaches `ACTIVE` (sslip.io resolves instantly, so this is typically
well under an hour, not the up-to-24h a real registrar can take).

### 5. Mint the Elasticsearch API key

The ES VM has no external IP, so tunnel in via IAP (your own gcloud user
needs `roles/iap.tunnelResourceAccessor` on the project for this):

```bash
gcloud compute ssh sadhana-elasticsearch --zone=<your-zone> --tunnel-through-iap -- \
  -L 9200:localhost:9200 -N &

ELASTIC_PASSWORD=$(gcloud secrets versions access latest --secret=es-elastic-password)
curl -s -u "elastic:${ELASTIC_PASSWORD}" -X POST "http://localhost:9200/_security/api_key" \
  -H "Content-Type: application/json" \
  -d '{"name": "sadhana-backend-runtime", "role_descriptors": {"search_only": {"index": [{"names": ["shlokas"], "privileges": ["read"]}]}}}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['encoded'])" \
  | gcloud secrets versions add es-api-key --data-file=-
```

Elasticsearch's create-API-key response includes an `encoded` field —
already `base64(id:api_key)` — which is exactly the string form the
`elasticsearch` Python client's `api_key=` parameter expects (see
`app/es_client.py`): a plain string is assumed pre-encoded, not `id:api_key`
raw. Store `encoded` as-is; don't re-derive or re-encode it.

### 6. Set up the index

```bash
uv run python -m ingest.run \
  --content-dir content/shlokas \
  --es-host http://localhost:9200 \
  --es-api-key "$(gcloud secrets versions access latest --secret=es-api-key)"
```

(Still through the IAP tunnel from step 5, or run this from inside the VPC.)

### 7. Set GitHub Actions repo variables

Under **Settings → Secrets and variables → Actions → Variables** in the
`sadhana-backend` repo:

| Variable | Example |
|---|---|
| `GCP_PROJECT_ID` | your project ID |
| `GCP_REGION` | `us-east1` |
| `GCP_ZONE` | `us-east1-b` |
| `WORKLOAD_IDENTITY_PROVIDER` | `projects/<number>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |

### 8. Push to `dev`

The deploy job builds+pushes the image and re-applies Terraform, which
points `sadhana-search-api` at the real image.

## After bootstrap

Every subsequent push to `dev` redeploys automatically. `main` never
redeploys — single-environment setup, `dev` is what's live.

## Risks / operating notes

- **Cost**: the ES VM and the LB's forwarding rules are the two fixed
  monthly costs regardless of traffic. Cloud Run scales to zero.
- **sslip.io is a third-party free service, not a Google product** — if it
  ever disappeared, the managed cert would stop renewing (certs auto-renew
  only while the domain keeps resolving correctly). Low risk for a widely-used
  service, but worth knowing; swapping to a real purchased domain later is a
  one-line change to `local.public_domain` in `lb.tf`.
- **Single-node ES has no HA** — deliberate, matches the plan's chosen
  hosting approach for this scale; a VM failure loses the index until
  re-ingested (cheap — the catalog is small and `ingest/run.py` is
  idempotent) or the persistent disk is reattached to a replacement VM.
