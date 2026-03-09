# Working Memory — voro-index-guard

> Keep under 40 lines. Current state ONLY.

## Current State

- **Branch**: main
- **Status**: Operational. No active development task.
- **App**: FastAPI on port 8080, 1,365 LOC, 504 test LOC
- **Tests**: 6 test files

## Architecture

- Standalone FastAPI code indexing service
- HMAC-SHA256 signing (Ed25519 migration planned)
- 8-language symbol extraction
- Strict trust mode (default)

## Blockers

- None

## Role Lock

- Codex: coding and testing
- Claude: analysis, planning, GitHub operations

## References

- Architectural Reference: `CLAUDE.md`
- Cross-repo roadmap: `~/.claude/VORO_PRODUCT_MASTER_PLAN.md`
