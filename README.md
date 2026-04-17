# voro-guard

This repository is the home of `voro-mcp`, an MCP server for code
intelligence, Solidity call graphs, and signed artifact/state retrieval.

If you found this repo through the MCP ecosystem, the main thing to know is:
`voro-mcp` gives clients authenticated access to indexed code, symbol lookup,
repository outlines, Solidity call graphs, and signed state artifacts through
one MCP surface.

`voro-mcp` does **not** provide:

- full VORO scan execution
- product-grade findings
- `scan_repo`
- `voro-shield` capability
- Bayesian scoring

## What `voro-mcp` Exposes Today

Current `voro-mcp` capabilities:

- repository indexing
  Plain English: register a repo or docs corpus so it can be queried later.
- symbol search and retrieval
  Plain English: find functions, classes, and other symbols by name, then fetch
  their details.
- repository outline
  Plain English: list files and extracted symbols for an indexed artifact.
- Solidity call graphs
  Plain English: inspect contract call relationships from indexed Solidity code.
- signed artifact and state retrieval
  Plain English: read signed learning-state, governance-report, and hydration
  artifacts that were already produced elsewhere.

The main MCP tools currently exposed by `app.mcp_server` are:

- `index_repo`
- `search_symbols`
- `get_symbol`
- `outline_file`
- `index_docs`
- `search_docs`
- `get_doc_section`
- `outline_docs`
- `publish_learning_state`
- `publish_work_state`
- `read_learning_state`
- `list_learning_states`
- `read_governance_report`
- `list_governance_reports`
- `hydrate_session`

## Install

Install locally from this repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

Install from PyPI after first public release:

```bash
pip install voro-mcp
```

## Run

Start the MCP stdio server:

```bash
voro-mcp
```

Equivalent module entry:

```bash
python -m app.mcp_server
```

## Runtime Model

`voro-mcp` is a stdio MCP wrapper over the authenticated `voro-guard` HTTP
service.

- default managed local mode starts the FastAPI service locally
- external mode reuses an already-running `voro-guard` service
- bearer auth is enforced by the underlying HTTP service

Relevant environment variables:

- `CODE_INDEX_SERVICE_TOKEN`
- `INDEX_GUARD_TOKEN`
- `INDEX_GUARD_URL`
- `CODE_INDEX_SIGNING_KEY`

## Local Development

Prerequisites:

- Python 3.12
- `pip`

Basic local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/unit/
```

Run the HTTP service directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Quick local checks:

```bash
pytest tests/unit/
curl -sS http://127.0.0.1:8080/health
```

## Repository Layout

- `app/main.py` — FastAPI app setup
- `app/mcp_server.py` — MCP stdio server and managed local runtime
- `app/routes/` — HTTP route handlers
- `app/core/` — indexing, parsing, signing, artifact, and call graph logic
- `docs/CODEBASE_MAP.md` — repo structure reference

## Project Context

- The public package name is `voro-mcp`.
- The current launch-facing MCP server identity is
  `io.github.voro-security/voro-mcp`.
- `voro-guard` is the underlying service and runtime that powers the public
  `voro-mcp` package.
- Some public-facing metadata in this repo is prepared for a future
  `voro-security/voro-guard` GitHub owner path; do not treat that as proof of a
  completed repo transfer until it actually happens.
