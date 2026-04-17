# voro-guard

## What This Repo Is

This repository is the home of `voro-mcp`, an MCP server for code
intelligence, Solidity call graphs, and signed artifact/state retrieval.

If you found this repo through the MCP ecosystem, the main thing to know is:
`voro-mcp` gives clients authenticated access to indexed code, symbol lookup,
repository outlines, Solidity call graphs, and signed state artifacts through
one MCP surface.

`voro-mcp` does **not** provide:

- full repository vulnerability scanning
- product-grade findings
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

The main MCP tools currently exposed by `voro_mcp.mcp_server` are:

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

## Quick Start

Install locally from this repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
voro-mcp
```

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
python -m voro_mcp.mcp_server
```

## First Run With An MCP Client

`voro-mcp` is meant to be started by an MCP client over stdio. A minimal
client entry looks like this:

```json
{
  "mcpServers": {
    "voro-mcp": {
      "command": "voro-mcp"
    }
  }
}
```

On first run, the server starts the bounded `voro-guard` runtime locally
unless you point it at an existing service with `INDEX_GUARD_URL`.

## Runtime Model

`voro-mcp` is a stdio MCP wrapper over the authenticated `voro-guard` HTTP
service.

- default managed local mode starts the FastAPI service locally
- external mode reuses an already-running `voro-guard` service
- bearer auth is enforced by the underlying HTTP service

Relevant environment variables:

- `CODE_INDEX_SERVICE_TOKEN` — usually required when auth is enabled
- `INDEX_GUARD_URL` — optional; points `voro-mcp` at an already-running
  `voro-guard` service instead of managed local mode
- `INDEX_GUARD_TOKEN` — optional override for the upstream bearer token
- `CODE_INDEX_SIGNING_KEY` — required only for strict signed-artifact and
  signed-state flows

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
uvicorn voro_mcp.main:app --host 0.0.0.0 --port 8080
```

Quick local checks:

```bash
pytest tests/unit/
curl -sS http://127.0.0.1:8080/health
```

## Test

Use these quick checks after a local setup or runtime change:

```bash
pytest tests/unit/
curl -sS http://127.0.0.1:8080/health
```

## Fleet Role

- `voro-guard` is the underlying service and runtime that powers the public
  `voro-mcp` package.
- Internal systems such as `voro-brain` may consume this surface, but public
  users do not need access to private repositories to install or run
  `voro-mcp`.

## Key Paths

- `voro_mcp/main.py` — FastAPI app setup
- `voro_mcp/mcp_server.py` — MCP stdio server and managed local runtime
- `voro_mcp/routes/` — HTTP route handlers
- `voro_mcp/core/` — indexing, parsing, signing, artifact, and call graph logic
- `docs/CODEBASE_MAP.md` — repo structure reference

## Documentation

- `README.voro-mcp.md` — package-facing README for the public `voro-mcp`
  install surface
- `docs/CODEBASE_MAP.md` — generated structural reference for the repo
- `docs/DEPLOY_ZEABUR.md` — Zeabur deployment reference for the underlying
  service runtime

## Project Context

- The public package name is `voro-mcp`.
- The current launch-facing MCP server identity is
  `io.github.voro-security/voro-mcp`.
- `voro-guard` is the underlying service and runtime that powers the public
  `voro-mcp` package.
