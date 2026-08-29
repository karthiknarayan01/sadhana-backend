#!/bin/bash
# Deploys/redeploys the search-api container on this VM to the image tag
# given as $1. search-api runs alongside Elasticsearch on this one VM (see
# elasticsearch.tf) instead of on Cloud Run, so unlike Cloud Run nothing
# redeploys it for you on a new image tag — the deploy workflow's job is to
# make that happen: it scp's this file fresh on every push to dev (so the
# VM always runs the current version of this script, not a stale copy) and
# then SSHes in to execute it (see .github/workflows/ci.yml).
#
# No gcloud CLI here deliberately, same as es-startup.sh — it isn't
# preinstalled on this base image, so auth goes through the metadata
# server's own token endpoint plus raw REST calls instead.
set -euo pipefail

IMAGE_TAG="${1:?usage: redeploy-api.sh <image-tag>}"
METADATA="http://metadata.google.internal/computeMetadata/v1"

PROJECT_ID=$(curl -s -H "Metadata-Flavor: Google" "${METADATA}/project/project-id")
REGION=$(curl -s -H "Metadata-Flavor: Google" "${METADATA}/instance/attributes/region")
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/sadhana-backend-images/search-api:${IMAGE_TAG}"

TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "${METADATA}/instance/service-accounts/default/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "${TOKEN}" | docker login -u oauth2accesstoken --password-stdin "https://${REGION}-docker.pkg.dev"

# Same secret es-startup.sh's Elasticsearch container gets its own
# credential from — see secrets.tf. Not yet minted the very first time this
# runs (see infra README's "mint the Elasticsearch API key" step): skip
# starting search-api rather than run it with no working credential.
ES_API_KEY=$(curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/es-api-key/versions/latest:access" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())" 2>/dev/null) \
  || ES_API_KEY=""

if [ -z "${ES_API_KEY}" ]; then
  echo "es-api-key has no version yet — not starting search-api. Mint it (see infra README), then re-run this deploy." >&2
  exit 0
fi

docker pull "${IMAGE}"
# Not `docker restart` — an existing container is pinned to whatever image
# it was created from, so picking up a new tag means recreating it. This is
# the deploy's downtime window: old container gone, new one not yet
# serving, until `docker run` below finishes starting it.
docker rm -f search-api >/dev/null 2>&1 || true
docker run -d --name search-api --restart=always \
  -p 8080:8080 \
  -e ES_HOST="http://localhost:9200" \
  -e ES_INDEX="shlokas" \
  -e ES_API_KEY="${ES_API_KEY}" \
  "${IMAGE}"

echo "search-api now running ${IMAGE}."
