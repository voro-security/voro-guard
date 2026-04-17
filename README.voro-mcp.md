# voro-mcp

mcp-name: io.github.voro-security/voro-mcp

`voro-mcp` is the publishable MCP install surface for the current
`voro-guard` capability only.

It exposes the existing `voro-guard` MCP stdio wrapper as an installable
Python package so MCP clients can access:

- repository indexing
- symbol search, get, and outline
- Solidity call graph generation
- signed artifact-backed learning-state retrieval
- signed governance-report retrieval
- session hydration / signed state assembly

This package does **not** claim:

- `voro-shield`
- full VORO scan execution
- product-grade findings
- Bayesian scoring
- broader VORO web-product capability

## Install

Local review install:

```bash
pip install .
```

Published install surface after first package release:

```bash
pip install voro-mcp
```

## Run

```bash
voro-mcp
```

Equivalent direct module entry:

```bash
python -m app.mcp_server
```

## Runtime boundary

`voro-mcp` is a stdio MCP wrapper over the authenticated `voro-guard` HTTP
service.

- default managed local mode starts the FastAPI service locally
- external mode reuses an already-running `voro-guard` service
- Bearer auth is still enforced by the underlying `/v1/*` HTTP service

Relevant environment variables:

- `CODE_INDEX_SERVICE_TOKEN`
- `INDEX_GUARD_TOKEN`
- `INDEX_GUARD_URL`
- `CODE_INDEX_SIGNING_KEY`

## Truthful capability summary

`voro-mcp` gives AI agents and security workflows authenticated access to:

- indexed code intelligence
- symbol-level retrieval
- Solidity call graphs
- trust-signed artifact retrieval
- hydration-backed signed state assembly

It remains the `voro-guard` transport, verification, and retrieval plane. It
is not the semantic authority for the underlying repos or documents it serves.
