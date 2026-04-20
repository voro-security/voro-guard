# VORO Index Guard — Claude Code Context Anchor

> **After compaction:** Read this ENTIRE file + `.claude/rules/working-memory.md` before doing anything.
> **After session resume:** Re-read this file to re-orient.

## Identity

- **Repo:** voro-guard (code indexing & artifact trust service)
- **Role:** Standalone hardened code-index service with artifact signing, symbol extraction, call graph analysis, and token-savings estimates
- **Language:** Python 3.12, FastAPI, Pydantic, FastMCP
- **Tests:** 8 unit test modules (`pytest tests/unit/`)
- **Entry points:** `uvicorn voro_mcp.main:app` (HTTP API) / `python -m voro_mcp.mcp_server` (MCP stdio)
- **Public package/listing identity:** `voro-mcp` / `io.github.voro-security/voro-mcp`
- **Version:** 0.1.0

## Architecture Contract

Three product repos + voro-guard as infrastructure service. No cross-repo Python imports. JSON over CLI/HTTP/MCP.

| Repo | Role | Interface |
|------|------|-----------|
| **voro-scan** | Scanner CLI (binary: agent-builder) | `agent-builder audit <target> --json` → audit JSON |
| **voro-brain** | Intelligence layer | Calls voro-guard via MCP stdio subprocess |
| **voro-web** | Web product | Renders ThreatReports from voro-brain |
| **voro-guard** | Code index service | HTTP REST API + MCP stdio wrapper |

**voro-brain is the primary consumer.** It spawns `python -m voro_mcp.mcp_server` as a subprocess and communicates via MCP stdio protocol. The MCP server manages a FastAPI subprocess on `127.0.0.1:18765`.

Endpoint authority:
- `127.0.0.1:18765` is the managed local hydration/publish endpoint used by startup and closeout flows.
- `127.0.0.1:8080` is the direct FastAPI HTTP surface and core health endpoint.

## Architecture Role

voro-guard is a **service** called by voro-brain via MCP stdio subprocess. It is never imported as a Python module by any other repo.

```
voro-brain (ExploitabilityAssessor)
  → spawns: python -m voro_mcp.mcp_server (stdio)
    → MCP server starts managed FastAPI subprocess on 127.0.0.1:18765
      → index_repo() → POST /v1/index → ArtifactEnvelope
      → search_symbols() → POST /v1/search → SymbolMatch[]
      → get_symbol() → POST /v1/get → Symbol
      → outline_file() → POST /v1/outline → FileOutline
      → callgraph() → POST /v1/callgraph → CallGraph
```

## HTTP API Contract

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/health` | Service health check | No |
| POST | `/v1/index` | Index a repository (code or docs), create signed artifact | Bearer |
| POST | `/v1/learning-state` | Publish signed adaptive-learning backplane state | Bearer / toggle-gated |
| GET | `/v1/learning-state/{artifact_id}` | Read signed adaptive-learning state artifact | Bearer / toggle-gated |
| GET | `/v1/learning-states` | List signed adaptive-learning state artifacts | Bearer / toggle-gated |
| POST | `/v1/search` | Search symbols (code) or sections (docs) by query | Bearer |
| POST | `/v1/get` | Get symbol by ID (code) or doc/section by ID (docs) | Bearer |
| POST | `/v1/outline` | List files/symbols (code) or documents/sections (docs) | Bearer |
| POST | `/v1/callgraph` | Build Solidity call graph from file | Bearer |
| GET | `/v1/hydrate` | Assemble hydration response (system/repo/work state) | Bearer |
| GET | `/v1/metrics` | Service metrics snapshot | Bearer |

## MCP Tools (exposed via stdio)

The repo/runtime remains `voro-guard`, but the public-facing MCP server identity
exposed from `voro_mcp.mcp_server` is `io.github.voro-security/voro-mcp`.

| Tool | Maps To | Purpose |
|------|---------|---------|
| `index_repo(source_type, source_id, workspace_id, source_revision)` | POST `/v1/index` | Index a repository |
| `search_symbols(query, workspace_id, artifact_id, source_fingerprint)` | POST `/v1/search` | Search symbols |
| `get_symbol(symbol_id, workspace_id, artifact_id, source_fingerprint)` | POST `/v1/get` | Get symbol detail |
| `outline_file(workspace_id, artifact_id, source_fingerprint)` | POST `/v1/outline` | File/symbol outline |
| `index_docs(source_type, source_id, workspace_id, source_revision)` | POST `/v1/index` | Index docs, return signed `docs-v1` artifact |
| `search_docs(query, workspace_id, artifact_id, source_fingerprint, allowed_visibility)` | POST `/v1/search` | Search doc sections by heading/keyword/summary |
| `get_doc_section(workspace_id, artifact_id, doc_id, section_id, source_fingerprint, allowed_visibility)` | POST `/v1/get` | Get specific document or section |
| `outline_docs(workspace_id, artifact_id, source_fingerprint, allowed_visibility)` | POST `/v1/outline` | Outline docs artifact |
| `publish_learning_state(workspace_id, source_id, state_type, payload, metadata)` | POST `/v1/learning-state` | Publish adaptive-learning state |
| `read_learning_state(workspace_id, artifact_id)` | GET `/v1/learning-state/{artifact_id}` | Read adaptive-learning state |
| `list_learning_states(workspace_id, source_id, state_type, limit)` | GET `/v1/learning-states` | List adaptive-learning state artifacts |
| `hydrate_session(workspace_id, agent_id, repo, worktree_path, workspace_root)` | GET `/v1/hydrate` | Assemble session resume state bundle |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CODE_INDEX_TRUST_MODE` | `strict` | `strict` (signed verification) or `legacy` (unsigned allowed) |
| `CODE_INDEX_SIGNER` | `voro-guard` | Signing identity |
| `CODE_INDEX_SIGNING_KEY` | `` | HMAC secret for artifact signing (required in strict mode) |
| `CODE_INDEX_SERVICE_TOKEN` | `` | Bearer token for HTTP API auth |
| `CODE_INDEX_GITHUB_TOKEN` | `` | GitHub PAT for private repos |
| `CODE_INDEX_MAX_FILES` | `400` | Max files to index per repo |
| `CODE_INDEX_MAX_FILE_SIZE_BYTES` | `512000` | Max file size (500 KB) |
| `CODE_INDEX_MAX_SYMBOLS_PER_FILE` | `200` | Max symbols per file |
| `CODE_INDEX_INDEX_TIMEOUT_SECONDS` | `30` | Indexing timeout |
| `ARTIFACT_ROOT` | `./data/artifacts` | Artifact storage directory |

## Validation

Run these after API, MCP, signing, or artifact-schema changes:

```bash
pytest tests/unit/
uvicorn voro_mcp.main:app --host 0.0.0.0 --port 8080
python -m voro_mcp.mcp_server
```

## Architectural Reference (eliminates re-exploration)

## Repo Structure

```
voro-guard/
├── voro_mcp/                              # Main application (~1,541 LOC)
│   ├── main.py                       # FastAPI app setup (15L)
│   ├── config.py                     # Settings/env config (19L)
│   ├── security.py                   # Bearer token auth (19L)
│   ├── metrics.py                    # Request/success/deny counters (74L)
│   ├── mcp_server.py                 # FastMCP stdio wrapper + managed subprocess (331L)
│   ├── models/
│   │   └── schemas.py                # Pydantic request/response models (160L)
│   ├── routes/
│   │   ├── index.py                  # POST /v1/index, artifact signing (125L)
│   │   ├── learning.py               # Adaptive-learning backplane publish/read/list routes
│   │   ├── hydration.py              # Hydration plane — session resume protocol (GET /v1/hydrate)
│   │   └── query.py                  # Search/get/outline/metrics/callgraph (160L)
│   └── core/                         # Business logic
│       ├── artifacts.py              # Artifact persistence & verification (130L)
│       ├── callgraph.py              # Solidity call graph analysis (209L)
│       ├── identity.py               # Source fingerprinting (71L)
│       ├── indexer.py                # GitHub & local repo indexing (263L)
│       ├── ingest.py                 # File discovery & reading (61L)
│       ├── parser.py                 # Symbol extraction, 8 languages (169L)
│       ├── safety.py                 # Symlink/secret/binary checks (70L)
│       ├── signing.py                # HMAC-SHA256 signing (22L)
│       ├── store.py                  # Symbol indexing & querying (113L)
│       ├── docs_ingest.py            # Docs markdown discovery with safety checks (69L)
│       ├── docs_parser.py            # Docs section extraction, metadata, visibility (249L)
│       └── docs_store.py             # Docs payload assembly, search, retrieval, outline (312L)
├── data/
│   └── artifacts/                    # Persisted signed artifacts (JSON)
├── docs/
│   └── DEPLOY_ZEABUR.md              # Production deployment guide
├── scripts/
│   └── smoke_prod.sh                 # Production smoke test
├── tests/
│   └── unit/                         # 12 test modules (85 tests)
│       ├── test_auth.py              # Bearer token auth
│       ├── test_callgraph.py         # Solidity call graph
│       ├── test_github_indexer.py    # GitHub repo indexing
│       ├── test_incremental_github_phaseb.py  # Incremental rebuild
│       ├── test_indexer_runtime.py   # Local indexing + querying
│       ├── test_mcp_server.py        # MCP server lifecycle (code + docs tools)
│       ├── test_perf_caps.py         # Performance limits
│       ├── test_trust_guard.py       # Artifact trust verification
│       ├── test_docs_parser.py       # Docs parser: sections, metadata, visibility
│       ├── test_docs_indexer_runtime.py  # Docs end-to-end: discover → parse → index → search → get → outline
│       ├── test_docs_trust_guard.py  # Docs trust: sign/verify round-trip, tamper detection
│       └── test_hydration.py         # Hydration plane: freshness, state assembly, identity filtering
├── README.md
├── requirements.txt                  # Python deps (FastAPI, uvicorn, httpx, fastmcp, pydantic)
├── Dockerfile                        # Python 3.12-slim
└── openapi.json                      # Auto-generated OpenAPI 3.0 schema
```

## Key Data Contracts

### ArtifactEnvelope (output of POST /v1/index)

```json
{
  "schema_version": "c35-v1",
  "workspace_id": "ws1",
  "source_type": "github|git|local_repo|snapshot",
  "source_id": "owner/repo or path",
  "source_revision": "commit_sha",
  "source_fingerprint": "sha256:...",
  "repo_fingerprint": "sha256:...",
  "artifact_id": "24-char sha256 prefix",
  "artifact_version": 3,
  "rebuild_reason": "incremental_changed_files",
  "artifact_hash": "sha256 hex",
  "manifest": {
    "signer": "voro-guard",
    "signed_at": "ISO8601",
    "signature": "hmac_hex",
    "key_id": null
  },
  "payload": {
    "files": [{"path", "language", "line_count", "approx_tokens", "blob_sha"}],
    "symbols": [{"id", "kind", "name", "file", "line", "language", "snippet", "visibility", "payable", "reachable"}],
    "stats": {"file_count", "symbol_count"},
    "token_savings_estimate": {"baseline_tokens_est", "indexed_tokens_est", "saved_tokens_est", "saved_percent_est"},
    "index_meta": {"strategy", "incremental": {"changed_files", "reused_files", "deleted_files"}}
  }
}
```

### Symbol Fields (cross-repo contract with voro-brain)

| Field | Type | Note |
|-------|------|------|
| `id` | string | 24-char SHA256 prefix |
| `kind` | string | function, class, interface, contract |
| `name` | string | Symbol name |
| `file` | string | File path within repo |
| `line` | int | Line number |
| `language` | string | python, javascript, typescript, go, rust, java, php, solidity |
| `snippet` | string | Source code context (±2 lines) |
| `visibility` | string | Solidity only: public, external, internal, private |
| `payable` | bool | Solidity only |
| `reachable` | bool | Solidity only — from call graph analysis |

### Docs Artifact (`docs-v1`)

Docs artifacts use `schema_version: "docs-v1"` and are created via `/v1/index` with `index_kind: "docs"`. They share the same signing, trust, and persistence infrastructure as code artifacts.

Payload shape: `documents[]` (doc_id, path, title, status, class, authority, visibility) + `sections[]` (section_id, heading, heading_path, start_line, end_line, summary, keywords, visibility).

Visibility tiers: `public`, `pro`, `enterprise`, `internal`. Document-level in v1; sections inherit parent document visibility. Retrieval interfaces filter by `allowed_visibility`.

Binding spec: `voro-docs/DOCS_INDEXING_SPEC.md`.

### Learning Artifacts (`learning-v1`)

Adaptive-learning backplane state uses `schema_version: "learning-v1"` and the same artifact envelope, signing, and persistence infrastructure as code/docs artifacts.

The payload remains publisher-defined and opaque at the service layer. Guard stores:
- `state_type`
- `metadata`
- `payload`

MCP publishes learning state through `publish_learning_state()` and reads it back through `read_learning_state()` / `list_learning_states()`, which proxy directly to the `/v1/learning-state*` HTTP surfaces.

The feature toggle is `VORO_ADAPTIVE_LEARNING`. When disabled, `/v1/learning-state*` returns `404 {"reason":"adaptive_learning_disabled"}` with zero behavior change to the rest of the service.

## Supported Languages

Python, JavaScript, TypeScript, Go, Rust, Java, PHP, Solidity

Symbol extraction is regex-based (line-by-line parsing, no AST). Solidity has additional call graph analysis with visibility/reachability metadata.

## Security Model

1. **Artifact Signing:** HMAC-SHA256 over canonical JSON (deterministic field ordering)
2. **Trust Modes:** `strict` (signature required) vs `legacy` (unsigned allowed, dev only)
3. **Bearer Token Auth:** Required for all /v1/* endpoints when `CODE_INDEX_SERVICE_TOKEN` set
4. **Path Safety:** Symlink escape detection, secret file filtering, binary exclusion
5. **Identity Verification:** workspace_id + source_fingerprint + artifact_id verified on queries

## Guardrails

- Import this repo's code from any other VORO repo — use MCP/HTTP only
- Disable strict trust mode in production
- Store artifacts without signing in production
- Expose the signing key in logs, tests, or config files
- Add AST parsing — regex extraction is intentional for speed and portability
- Break the MCP stdio contract that voro-brain depends on
- Modify the ArtifactEnvelope schema without updating voro-brain consumers

## Cross-Repo Awareness

- `voro-brain` is the primary consumer and calls this repo via MCP stdio subprocess
- `voro-web` does not consume this service directly; it depends on `voro-brain` output instead
- Artifact and symbol contracts must remain stable for downstream exploitability logic

## Session Start

1. `git status --short --branch`
2. Read this file and `.claude/rules/working-memory.md`
3. Check whether the task touches HTTP API, MCP wrapper, or artifact schema
4. Run `pytest tests/unit/` before closing structural changes

## Build & Run

```bash
# For local development, prefer repo-local direnv loading:
#   cp .envrc.example .envrc
#   eval "$(../voro-core/scripts/bw-unlock.sh)"
#   direnv allow
#
pip install -r requirements.txt                         # Install deps
pytest tests/unit/                                      # Run tests
uvicorn voro_mcp.main:app --host 0.0.0.0 --port 8080       # Run HTTP API
python -m voro_mcp.mcp_server                                # Run MCP stdio server
docker build -t voro-guard . && docker run \
  -e CODE_INDEX_SIGNING_KEY=... \
  -e CODE_INDEX_SERVICE_TOKEN=... \
  -p 8080:8080 voro-guard                              # Docker
```

## Deployment

Production via Zeabur (see `docs/DEPLOY_ZEABUR.md`):
- Docker image from Dockerfile
- Port 8080 exposed
- Required env vars: `CODE_INDEX_SERVICE_TOKEN`, `CODE_INDEX_SIGNING_KEY`, `CODE_INDEX_TRUST_MODE=strict`
- Persistent volume at `/data/artifacts`
- Health check: `GET /health` → 200

## Current State

- **Branch:** `main` at `45cdb1d`
- Phase 2.0 (MCP wrapper) merged
- Phase 3.0 (Solidity call graphs with visibility) merged (#6)
- Known issues: voro-guard#5 (visibility modifier parsing for reachability)
- Integration: voro-brain calls via `src/exploitability/index_guard_client.py` (gated by `VORO_EXPLOITABILITY=1`)

## Cross-Tool Architectural Constraints

These rules apply to all AI tools (Claude, Gemini, Codex) operating in this repo.

### Architectural Boundaries (Strict Decoupling)
- No cross-repo imports. MCP/HTTP only.
- voro-brain is the consumer — do not modify voro-brain from this repo.

### Security Guardrails
- Never commit signing keys, service tokens, or GitHub PATs to version control.
- Never print or expose env vars containing keys/tokens.
- Treat all artifact data and signing material as confidential.
- Do not store optional project secrets in global shell startup files; use repo-local `.envrc` and a secret manager.

### Workspace Canonical Path

This repo's canonical root is `/home/alienblackunix/dev/voro/voro-guard`. If your working directory is not this path, stop and ask.

## Compaction Recovery

1. Read this file (you're doing that now)
2. Read `.claude/rules/working-memory.md` for current task
3. Check `git diff` and `git log --oneline -10`
4. Run `pytest tests/unit/` to verify nothing is broken
5. Resume from working-memory.md current task
