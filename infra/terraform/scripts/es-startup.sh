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
