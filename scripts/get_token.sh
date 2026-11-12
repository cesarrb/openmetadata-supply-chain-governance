#!/usr/bin/env bash
# Logs in with the local default admin account and stores the ingestion-bot JWT in .om_token (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
OM=${OM_URL:-http://localhost:8585}
P=$(printf "${OM_ADMIN_PASSWORD:-admin}" | base64)
T=$(curl -sf -X POST $OM/api/v1/users/login -H 'Content-Type: application/json' \
     -d "{\"email\":\"${OM_ADMIN_EMAIL:-admin@open-metadata.org}\",\"password\":\"$P\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["accessToken"])')
BOT=$(curl -sf $OM/api/v1/bots/name/ingestion-bot -H "Authorization: Bearer $T" | python3 -c 'import sys,json;print(json.load(sys.stdin)["botUser"]["id"])')
curl -sf $OM/api/v1/users/auth-mechanism/$BOT -H "Authorization: Bearer $T" | python3 -c 'import sys,json;print(json.load(sys.stdin)["config"]["JWTToken"])' > .om_token
echo "Token saved to .om_token"
