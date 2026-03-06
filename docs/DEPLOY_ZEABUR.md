# Deploy on Zeabur

## Service Type
- Git repository deploy
- Dockerfile: `Dockerfile`
- Exposed HTTP port: `8080`

## Required Environment Variables
- `CODE_INDEX_SERVICE_TOKEN=<strong-random-token>`
- `CODE_INDEX_SIGNING_KEY=<strong-random-signing-key>`
- `CODE_INDEX_TRUST_MODE=strict`
- `CODE_INDEX_SIGNER=voro-index-guard-prod`
- `ARTIFACT_ROOT=/data/artifacts`

## Optional Environment Variables
- `CODE_INDEX_TRUST_MODE=legacy` (non-production only)

## Health Check
- Path: `/health`
- Expected: `200` with JSON payload

## Persistence
- Attach Zeabur volume for `/data/artifacts`

## Smoke Checks
```bash
curl -sS https://<service-domain>/health

curl -sS -X POST https://<service-domain>/v1/index \
  -H "Authorization: Bearer <CODE_INDEX_SERVICE_TOKEN>" \
  -H "content-type: application/json" \
  -d '{"workspace_id":"ws1","repo_fingerprint":"sha256:abc"}'
```
