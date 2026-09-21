#!/bin/bash
# Runs once on first boot (GCE startup-script metadata). Installs Docker and
# runs a single-node Elasticsearch container with security enabled, using
# the bootstrap password from Secret Manager (populated by hand before the
# VM is first created — see infra README's "First-time bootstrap").
#
# --restart=always means a VM reboot (e.g. after a maintenance event) brings
# the container back up on its own; this script itself only runs once.
set -euo pipefail

apt-get update
apt-get install -y docker.io
systemctl enable docker
systemctl start docker

METADATA="http://metadata.google.internal/computeMetadata/v1"
TOKEN=$(curl -s -H "Metadata-Flavor: Google" \
  "${METADATA}/instance/service-accounts/default/token" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
PROJECT_ID=$(curl -s -H "Metadata-Flavor: Google" "${METADATA}/project/project-id")

ELASTIC_PASSWORD=$(curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/es-elastic-password/versions/latest:access" \
  | python3 -c "import sys,json,base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode())")

# The data disk is attached but unformatted on first boot only.
DISK_DEVICE="/dev/disk/by-id/google-es-data"
MOUNT_POINT="/mnt/disks/es-data"
mkdir -p "${MOUNT_POINT}"
if ! blkid "${DISK_DEVICE}" >/dev/null 2>&1; then
  mkfs.ext4 -F "${DISK_DEVICE}"
fi
mount -o discard,defaults "${DISK_DEVICE}" "${MOUNT_POINT}"
echo "${DISK_DEVICE} ${MOUNT_POINT} ext4 discard,defaults,nofail 0 2" >> /etc/fstab
# The container runs as the elasticsearch image's uid 1000.
chown -R 1000:1000 "${MOUNT_POINT}"

docker run -d --name elasticsearch --restart=always \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=true \
  -e ELASTIC_PASSWORD="${ELASTIC_PASSWORD}" \
  -e ES_JAVA_OPTS="-Xms768m -Xmx768m" \
  -v "${MOUNT_POINT}:/usr/share/elasticsearch/data" \
  docker.elastic.co/elasticsearch/elasticsearch:8.15.0

# Cache warm-up: the corpus is small enough (a few hundred shlokas, each
# well under 5MB) to sit entirely in the OS page cache, but that cache is
# only populated lazily as segment files get read — without this, whoever
# sends the first real search pays for the cold disk read. A size-10000
# match_all forces ES to read every document's stored _source off disk
# once here instead, right after boot. No-ops harmlessly (HTTP 404, no
# curl -f) if the index hasn't been created yet — e.g. this VM's very
# first boot, before `ingest/run.py` has been run by hand.
echo "Waiting for Elasticsearch to report healthy..."
until curl -s -u "elastic:${ELASTIC_PASSWORD}" \
    "http://localhost:9200/_cluster/health?wait_for_status=yellow&timeout=5s" \
    | grep -q '"timed_out":false'; do
  sleep 2
done

echo "Warming the page cache..."
curl -s -u "elastic:${ELASTIC_PASSWORD}" \
  -H "Content-Type: application/json" \
  "http://localhost:9200/shlokas/_search?size=10000" \
  -d '{"query": {"match_all": {}}}' \
  > /dev/null
echo "Cache warm-up done."

# Mint search-api's Elasticsearch credential here too, instead of requiring
# a human to SSH in and do it by hand — this SA already has both read
# access to es-api-key (redeploy-api.sh needs that) and add-version access
# to it (see elasticsearch.tf), and the elastic superuser password needed
# to create the key is already in scope above. Only ever does this once:
# skipped if a version already exists, so a from-scratch VM rebuilt against
# the *same* persistent ES data disk doesn't mint a second, redundant key.
EXISTING_API_KEY=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
  "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/es-api-key/versions/latest:access")
if echo "${EXISTING_API_KEY}" | grep -q '"name"'; then
  echo "es-api-key already has a version — not re-minting."
else
  echo "Minting the search-api Elasticsearch API key..."
  ENCODED_KEY=$(curl -s -u "elastic:${ELASTIC_PASSWORD}" -X POST "http://localhost:9200/_security/api_key" \
    -H "Content-Type: application/json" \
    -d '{"name": "sadhana-search-api", "role_descriptors": {"search_only": {"index": [{"names": ["shlokas"], "privileges": ["read"]}]}}}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['encoded'])")

  curl -s -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -X POST "https://secretmanager.googleapis.com/v1/projects/${PROJECT_ID}/secrets/es-api-key:addVersion" \
    -d "{\"payload\": {\"data\": \"$(printf '%s' "${ENCODED_KEY}" | base64)\"}}" \
    > /dev/null
  echo "es-api-key stored."
fi
