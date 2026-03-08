# voro-index-guard

FastAPI code indexing service — indexes repositories and provides symbol search/query capabilities for the VORO ecosystem.

---

## Quick Reference

```bash
# Run
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Run tests
pytest tests/

# Environment variables
CODE_INDEX_SERVICE_TOKEN=<bearer-token>   # Required in production
TRUST_MODE=strict                          # strict (default) | legacy
```

---

## Module Inventory

| Module | Purpose |
|--------|---------|
| `app/main.py` | FastAPI app setup, middleware, router registration |
| `app/config.py` | Configuration: caps, timeouts, limits |
| `app/security.py` | Bearer token auth via FastAPI dependency injection |
| `app/metrics.py` | Prometheus metrics exposition |
| `app/models/schemas.py` | Pydantic request/response models |
| `app/routes/index.py` | Index endpoint routes (`/v1/index`, `/v1/get`) |
| `app/routes/query.py` | Query/search endpoint routes (`/v1/search`, `/v1/query`, `/v1/outline`) |
| `app/core/artifacts.py` | Artifact envelope creation and validation |
| `app/core/identity.py` | Source identity and fingerprinting |
| `app/core/indexer.py` | Core indexing logic |
| `app/core/ingest.py` | Source ingestion pipeline |
| `app/core/parser.py` | Symbol extraction (8 languages) |
| `app/core/safety.py` | Input validation, trust mode enforcement |
| `app/core/signing.py` | HMAC-SHA256 signing (Ed25519 migration planned) |

**Scale:** ~1,365 lines of app code, ~504 lines of test code, 6 test files

---

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Health check |
| POST | `/v1/index` | Bearer | Index a source (github, git, local_repo, http_docs, feed, snapshot) |
| POST | `/v1/search` | Bearer | Search indexed content |
| GET | `/v1/get/{source_id}` | Bearer | Get indexed source by ID |
| POST | `/v1/outline` | Bearer | Get code outline/structure |
| POST | `/v1/query` | Bearer | Query indexed content |
| GET | `/v1/metrics` | None | Prometheus metrics |

---

## Configuration

### Caps and Limits (app/config.py)

| Setting | Value |
|---------|-------|
| `max_files` | 400 |
| `max_file_size_bytes` | 524288 (512 KB) |
| `max_symbols_per_file` | 200 |
| `index_timeout` | 30s |

### Symbol Extraction Languages

Python, JavaScript, TypeScript, Go, Rust, Java, PHP, Solidity (8 languages)

### Artifact Envelope Schema (`c35-v1`)

```
schema_version: c35-v1
workspace_id:   <id>
source_fingerprint: <hash>
artifact_hash:  <hash>
manifest:
  signer:    <signer-id>
  signature: <hmac-sha256>
payload:
  files:   [...]
  symbols: [...]
  stats:   {...}
```

### Incremental Rebuilds

GitHub blob SHA tracking for incremental rebuilds (Phase B — implemented).

---

## Security Model

### Bearer Token Auth

- Controlled by `CODE_INDEX_SERVICE_TOKEN` environment variable
- Enforced via FastAPI dependency injection in `app/security.py`
- If `CODE_INDEX_SERVICE_TOKEN` is unset, auth is skipped (development mode only)
- **Production requirement:** `CODE_INDEX_SERVICE_TOKEN` must always be set

### Signing

- HMAC-SHA256 via `app/core/signing.py`
- Ed25519 migration is planned and documented — do not build new features on HMAC-SHA256

### Trust Modes

| Mode | Behavior |
|------|---------|
| `strict` | Default. Fail-closed. Rejects untrusted input. |
| `legacy` | Permissive. For backward compatibility only. Never use in new production paths. |

---

## DO NOTs

- Do NOT disable strict trust mode in production
- Do NOT skip bearer token auth in production (`CODE_INDEX_SERVICE_TOKEN` must be set)
- Do NOT exceed caps without updating `app/config.py`
- Do NOT use HMAC-SHA256 for new signing features — plan for Ed25519 migration
- Do NOT import from sibling VORO repos — JSON over CLI/HTTP only
- Do NOT put business logic in route handlers — keep it in `app/core/`

---

## Architectural Reference

### Current State (as of 2026-03-08)

- **Service:** Operational FastAPI service on port 8080
- **Signing:** HMAC-SHA256 (Ed25519 migration pending)
- **Symbol extraction:** 8 languages, up to 200 symbols/file
- **Trust model:** strict (default), legacy (backward compat)
- **Auth:** Bearer token; dev mode skips auth when token unset
- **Incremental rebuilds:** GitHub blob SHA tracking implemented (Phase B)
- **Commits:** 13 commits on main

### Role in VORO Ecosystem

voro-index-guard is a standalone service. It does not import from any other VORO repo. Other services communicate with it via JSON over HTTP.

```
voro-* services
  → POST /v1/index  → voro-index-guard indexes code
  → POST /v1/search → returns symbol/content matches
  → POST /v1/query  → returns structured query results
```
