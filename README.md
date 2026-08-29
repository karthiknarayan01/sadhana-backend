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

### Crawling sources (`ingest/crawl/`, local-only)

Optional tooling that stages new entries from public-domain Sanskrit
sources, for review before they join `content/shlokas/`. It only ever reads
the Devanagari text — `content.english` is produced locally by mechanical
phonetic transliteration (`ingest/crawl/common.py:to_plain_english`), never
by translating meaning, and `meaning.*` is always left empty. Consistent
with "nothing here bulk-scrapes any single site" above: run this against a
few sources for modest amounts each (`--max-entries`), not once against one
site for everything it has.

```
uv run python -m ingest.crawl.run --source wikisource \
    --category स्तोत्राणि --category-label stotram \
    --max-entries 30 --contact-email you@example.com

uv run python -m ingest.crawl.run --source sanskritdocuments \
    --category-path /sanskrit/stotra/ --category-label stotram \
    --max-entries 30 --contact-email you@example.com
```

Output lands in `content/shlokas_staging/` (gitignored) — review it, then
move the entries you want into `content/shlokas/` and run `ingest/run.py`
as usual. vignanam.org is deliberately not a supported source: its
`robots.txt` explicitly disallows `ClaudeBot`/`anthropic-ai`.

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

Elasticsearch runs self-hosted on a single private GCE VM (no external IP) —
never exposed to the internet directly. This Cloud Run service is the only
public entry point, reaching Elasticsearch over a private VPC (Direct VPC
egress) with Cloud Armor rate-limiting incoming requests per-IP ahead of it.
See `infra/terraform/` and `infra/terraform/README.md` for the resources and
one-time manual bootstrap (state bucket, Workload Identity Federation, the
ES VM's bootstrap password and API key). Nothing there has been applied yet —
`terraform apply` is a deliberate, explicit, human-run step.
