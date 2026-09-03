# Sadhana Backend

A small, read-only search API backing the shloka/sutra search feature of the
[Sadhana app](https://github.com/karthiknarayan01/sadhana-app). Elasticsearch
is the only datastore — no Postgres, no user accounts, no writes at request
time.

## API

- `GET /search?q=<query>` — top 10 matches against `name.english` and
  `content.english` (search always happens in English; the response includes
  every language a matched document has, for the client to switch display
  language locally without a second request).
- `GET /health`

## Content sourcing

The original Sanskrit verses are public domain, but a translation is a
separate creative work with its own copyright the moment it's written —
independent of whether the source page is discoverable via a search engine.
Nothing here bulk-scrapes any single site. See `ingest/` below: every
ingested entry carries a mandatory `license` field, and only entries backed
by a public-domain/openly-licensed source (or an original translation
produced for this project and labeled as such) get indexed.

## Ingestion (`ingest/`, local-only — never deployed)

A directory of per-shloka YAML files, one file per entry, validated against
`ingest/schema.py` before touching Elasticsearch:

```yaml
id: argala-stotram
category: stotram
name:
  english: Argala Stotram
  devanagari: अर्गला स्तोत्रम्
content:
  english: "..."
  devanagari: "..."
meaning:
  english: "..."   # optional — the field where the copyright judgment call
                     # actually matters, kept separate from `content` on purpose
source_attribution:
  text_source: "..."
  translation_source: "..."
  license: public_domain   # required — public_domain | cc_by | cc_by_sa | original_translation
```

```
uv run python -m ingest.run --content-dir content/shlokas --dry-run   # validate only
uv run python -m ingest.run --content-dir content/shlokas --es-host http://localhost:9200
```

## Development

```
uv sync
uv run ruff check .
uv run pytest        # spins up a real Elasticsearch via testcontainers
uv run uvicorn app.main:app --reload
```

`dev` is the default/live branch; `main` only advances via a dev → main
promotion PR (see `.github/workflows/enforce-dev-to-main.yml`).

## Infra

Elasticsearch and search-api both run self-hosted on a single private GCE
VM (`e2-small`, no external IP) — never exposed to the internet directly.
A Google Cloud external HTTPS Load Balancer is the only public entry point
(`https://34-54-97-93.sslip.io`), terminating TLS via a free sslip.io-based
managed cert and reaching the VM over a private VPC, with Cloud Armor
rate-limiting incoming requests per-IP ahead of it. See `infra/terraform/`
and `infra/terraform/README.md` for the resources — already applied and
live for the `sadhana-backend-305666` project; every push to `dev`
redeploys automatically.

## Traffic visibility

The load balancer's backend service has request logging enabled
(`log_config` in `infra/terraform/lb.tf`) — every request (path, status,
latency, source IP) lands in Cloud Logging automatically, no app code
involved. In the GCP Console: **Monitoring → Dashboards** has an
auto-populated one for the load balancer (request count, latency, error
rate, chartable per day/week); **Logging → Logs Explorer**, filtered to
`resource.type="http_load_balancer"`, has the raw per-request log entries
for anything more specific.
