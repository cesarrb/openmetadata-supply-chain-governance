#!/usr/bin/env bash
# Runs an OpenMetadata ingestion workflow inside the ingestion container.
# Usage: scripts/run_ingestion.sh ingestion/01_postgres_metadata.yaml [ingest|profile|classify]
set -euo pipefail
cd "$(dirname "$0")/.."
cfg="$1"; cmd="${2:-ingest}"
[ -f .om_token ] || { echo "Missing .om_token (run scripts/get_token.sh)"; exit 1; }
docker exec openmetadata_ingestion mkdir -p /opt/dbt /tmp/om 2>/dev/null || docker exec -u root openmetadata_ingestion mkdir -p /opt/dbt /tmp/om
for f in manifest.json catalog.json run_results.json; do
  [ -f "dbt/target/$f" ] && docker cp "dbt/target/$f" openmetadata_ingestion:/opt/dbt/$f
done
OM_JWT="$(cat .om_token)" python3 -c 'import os,sys;print(open(sys.argv[1]).read().replace("${OM_JWT}",os.environ["OM_JWT"]))' "$cfg" > /tmp/om_wf.yaml
docker cp /tmp/om_wf.yaml openmetadata_ingestion:/tmp/om/wf.yaml && rm /tmp/om_wf.yaml
docker exec openmetadata_ingestion metadata "$cmd" -c /tmp/om/wf.yaml 2>&1 | grep -vE 'UserWarning|class .*BaseModel'
