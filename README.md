# voro-index-guard
Standalone hardened code-index service with artifact trust verification and token-savings estimates.

## Endpoints
- `GET /health`
- `POST /v1/index`
- `POST /v1/search`
- `POST /v1/get`
- `POST /v1/outline`
- `GET /v1/metrics`

## Production Defaults
- Fail-closed trust mode (`CODE_INDEX_TRUST_MODE=strict`)
- Signed artifact verification required
- Bearer token required when `CODE_INDEX_SERVICE_TOKEN` is set
- Workspace + repo fingerprint identity enforcement

## Deploy
See [docs/DEPLOY_ZEABUR.md](docs/DEPLOY_ZEABUR.md).
