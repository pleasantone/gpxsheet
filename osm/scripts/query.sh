#!/usr/bin/env bash
# Smoke-test the local Overpass instance with a small California query:
# fuel stations within ~3 km of the Mt Hamilton / Lick Observatory area.
#
# Usage:
#   ./scripts/query.sh                 # uses http://localhost:12345
#   ENDPOINT=http://host:port ./scripts/query.sh
set -euo pipefail

ENDPOINT="${ENDPOINT:-http://localhost:12345}"

read -r -d '' QUERY <<'OQL' || true
[out:json][timeout:60];
node(around:3000, 37.3414, -121.6429)["amenity"="fuel"];
out body;
OQL

echo "POST ${ENDPOINT}/api/interpreter"
echo "Query:"
echo "${QUERY}"
echo "---"

curl -fsS "${ENDPOINT}/api/interpreter" --data-urlencode "data=${QUERY}"
echo
