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

For local development, prefer `direnv` plus a secret manager instead of putting these
values in `~/.bashrc`. See `../.envrc.example` and
`/home/alienblackunix/dev/voro/voro-docs/docs/secrets.md`.

## Optional Environment Variables
- `CODE_INDEX_GITHUB_TOKEN=<github-token>` (for private repos / higher GitHub API limits)
- `CODE_INDEX_MAX_FILES=400`
- `CODE_INDEX_MAX_FILE_SIZE_BYTES=512000`
- `CODE_INDEX_MAX_SYMBOLS_PER_FILE=200`
- `CODE_INDEX_INDEX_TIMEOUT_SECONDS=30`
- `CODE_INDEX_TRUST_MODE=legacy` (non-production only)

## Health Check
- Path: `/health`
- Expected: `200` with JSON payload

## Persistence
- Attach Zeabur volume for `/data/artifacts`

## Smoke Checks
Use the repository script:

```bash
chmod +x scripts/smoke_prod.sh
./scripts/smoke_prod.sh https://<service-domain> <CODE_INDEX_SERVICE_TOKEN> <optional-repo-ref>
```

Manual equivalents:

```bash
curl -sS https://<service-domain>/health

curl -sS -X POST https://<service-domain>/v1/index \
  -H "Authorization: Bearer <CODE_INDEX_SERVICE_TOKEN>" \
  -H "content-type: application/json" \
  -d '{"workspace_id":"ws1","repo_fingerprint":"sha256:abc"}'
```

## Production Guardrails
- Run with `CODE_INDEX_TRUST_MODE=strict`
- Set `CODE_INDEX_SERVICE_TOKEN` (no anonymous access)
- Set `CODE_INDEX_SIGNING_KEY` (required for trusted artifacts)
- Mount persistent volume at `ARTIFACT_ROOT`
