#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <BASE_URL> <SERVICE_TOKEN> [REPO_REF]"
  echo "Example: $0 https://indexguard.example.com my-token https://github.com/octocat/Hello-World"
  exit 1
fi

BASE_URL="${1%/}"
SERVICE_TOKEN="$2"
REPO_REF="${3:-}"

AUTH_HEADER="Authorization: Bearer ${SERVICE_TOKEN}"
JSON_HEADER="content-type: application/json"

WORKSPACE_ID="smoke-ws"
REPO_FINGERPRINT="sha256:smoke-$(date +%s)"

echo "==> Health"
curl -fsS "${BASE_URL}/health" | tee /tmp/vig_health.json
echo

echo "==> Index"
if [[ -n "${REPO_REF}" ]]; then
  INDEX_BODY="{\"workspace_id\":\"${WORKSPACE_ID}\",\"repo_fingerprint\":\"${REPO_FINGERPRINT}\",\"repo_ref\":\"${REPO_REF}\"}"
else
  INDEX_BODY="{\"workspace_id\":\"${WORKSPACE_ID}\",\"repo_fingerprint\":\"${REPO_FINGERPRINT}\"}"
fi

INDEX_RESP="$(curl -fsS -X POST "${BASE_URL}/v1/index" -H "${AUTH_HEADER}" -H "${JSON_HEADER}" -d "${INDEX_BODY}")"
echo "${INDEX_RESP}" | tee /tmp/vig_index.json >/dev/null
echo "${INDEX_RESP}"
echo

ARTIFACT_ID="$(echo "${INDEX_RESP}" | python3 -c 'import sys,json; print(json.load(sys.stdin)["artifact_id"])')"
SYMBOL_ID="$(echo "${INDEX_RESP}" | python3 -c 'import sys,json; d=json.load(sys.stdin); s=d.get("payload",{}).get("symbols",[]); print(s[0]["id"] if s else "")')"

echo "==> Search"
SEARCH_RESP="$(curl -fsS -X POST "${BASE_URL}/v1/search" -H "${AUTH_HEADER}" -H "${JSON_HEADER}" -d "{\"workspace_id\":\"${WORKSPACE_ID}\",\"repo_fingerprint\":\"${REPO_FINGERPRINT}\",\"artifact_id\":\"${ARTIFACT_ID}\",\"query\":\"scan\"}")"
echo "${SEARCH_RESP}" | tee /tmp/vig_search.json >/dev/null
echo "${SEARCH_RESP}"
echo

if [[ -n "${SYMBOL_ID}" ]]; then
  echo "==> Get"
  curl -fsS -X POST "${BASE_URL}/v1/get" -H "${AUTH_HEADER}" -H "${JSON_HEADER}" \
    -d "{\"workspace_id\":\"${WORKSPACE_ID}\",\"repo_fingerprint\":\"${REPO_FINGERPRINT}\",\"artifact_id\":\"${ARTIFACT_ID}\",\"symbol_id\":\"${SYMBOL_ID}\"}" \
    | tee /tmp/vig_get.json
  echo
fi

echo "==> Outline"
curl -fsS -X POST "${BASE_URL}/v1/outline" -H "${AUTH_HEADER}" -H "${JSON_HEADER}" \
  -d "{\"workspace_id\":\"${WORKSPACE_ID}\",\"repo_fingerprint\":\"${REPO_FINGERPRINT}\",\"artifact_id\":\"${ARTIFACT_ID}\"}" \
  | tee /tmp/vig_outline.json
echo

echo "==> Metrics"
curl -fsS "${BASE_URL}/v1/metrics" -H "${AUTH_HEADER}" | tee /tmp/vig_metrics.json
echo

echo "Smoke checks complete."
