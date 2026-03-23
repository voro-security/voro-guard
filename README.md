# VORO Guard

Standalone hardened code-index service with artifact trust verification and token-savings estimates.

## What This Repo Is

`voro-guard` is the fleet code-index and artifact-trust service.

It indexes repositories, extracts symbols across supported languages, builds Solidity call graphs, and exposes that data through an HTTP API and MCP stdio wrapper.

This repo is primarily for:

- engineers maintaining symbol extraction, signing, and artifact trust
- `voro-brain` integration work for exploitability and reachability analysis
- operators deploying the service in local or hosted environments

## Quick Start

Prerequisites:

- Python 3.12
- `pip`
- `pre-commit` (for local hook enforcement)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push
pytest tests/unit/
```

Success looks like:

- unit tests pass
- `/health` responds locally
- MCP server starts without crashing

## Run

```bash
# Load repo-local secrets first if you use direnv:
#   cp .envrc.example .envrc
#   eval "$(../voro-core/scripts/bw-unlock.sh)"
#   direnv allow
#
# HTTP API
uvicorn app.main:app --host 0.0.0.0 --port 8080

# MCP stdio server
python -m app.mcp_server

# Production smoke test
./scripts/smoke_prod.sh https://<service-domain> <CODE_INDEX_SERVICE_TOKEN>
```

## Test

```bash
pytest tests/unit/
curl -sS http://127.0.0.1:8080/health
```

Use the health check as a quick runtime validation after API or config changes.

## Fleet Role

- `voro-guard` serves code intelligence and signed artifacts
- `voro-brain` is the primary consumer via MCP stdio
- `voro-web` depends on `voro-brain` output rather than talking to `voro-guard` directly

Primary interfaces:

- HTTP API on `/health`, `/v1/index`, `/v1/search`, `/v1/get`, `/v1/outline`, `/v1/callgraph`, `/v1/metrics`
- MCP stdio wrapper via `python -m app.mcp_server`

## Key Paths

- `app/main.py` — FastAPI app setup
- `app/mcp_server.py` — MCP stdio wrapper and managed subprocess logic
- `app/routes/` — HTTP route handlers
- `app/core/` — indexing, parsing, signing, artifacts, call graphs
- `docs/CODEBASE_MAP.md` — generated structural map

## Documentation

- `CLAUDE.md` — agent entrypoint and architecture constraints
- `docs/CODEBASE_MAP.md` — generated codebase map
- `docs/DEPLOY_ZEABUR.md` — deployment guide
- [secrets.md](/home/alienblackunix/dev/voro/voro-docs/docs/secrets.md) — workspace secret-management policy
