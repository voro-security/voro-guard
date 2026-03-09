# Conventions — voro-index-guard

## Mandatory Session Start
1. Read `CLAUDE.md` — full architectural reference. Never skip this.
2. Read `.claude/rules/working-memory.md` — current state.

## Architecture Rules
- This is a standalone FastAPI service. No cross-repo Python imports.
- All inter-service communication is JSON over HTTP or CLI subprocess.
- Strict trust mode is default. Never weaken trust in production paths.
- Bearer token auth must be enforced when CODE_INDEX_SERVICE_TOKEN is set.

## Code Style
- Pydantic models for all request/response schemas (app/models/schemas.py)
- FastAPI dependency injection for auth (app/security.py)
- Core logic in app/core/, routes in app/routes/
- Tests mirror app structure in tests/

## Working Memory Protocol
- Keep `.claude/rules/working-memory.md` under 40 lines
- Current state ONLY — move history to `.claude/archive/`
- Update on every branch change, task change, or blocker change

## Fixed Role Policy
- Codex: coding and testing
- Claude: analysis, planning, GitHub operations
- Gemini: analyst #2 when needed
