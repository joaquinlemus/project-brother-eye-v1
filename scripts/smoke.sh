#!/usr/bin/env bash
# Pruebas de humo después de cada despliegue.
set -euo pipefail
URL="${1:?uso: smoke.sh https://portal.xyz-lab.com}"
curl -fsS "$URL/healthz" | grep -q '"ok"'
code=$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/v1/sites")
[ "$code" = "401" ] || { echo "Se esperaba 401 sin token y llegó $code"; exit 1; }
echo "Smoke OK"
