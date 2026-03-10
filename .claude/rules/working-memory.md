# Working Memory — voro-guard

> **What this is**: Live session state. Auto-loaded into every Claude session prompt.
> **Rules**: Keep under 40 lines. Current state ONLY — no history, no changelogs.
> Update this file at session START (set branch/task) and session END (set result).

## Current State

- **Branch**: `main` @ `45cdb1d`
- **Task**: Docs bootstrap — CLAUDE.md + .claude/rules/ created
- **Tests**: 8 unit test modules in tests/unit/

## Recent Completed Work

- Phase 2.0: MCP stdio wrapper (PR #4, merged)
- Phase 3.0: Solidity call graph + visibility parsing (PR #6, merged)
- Docs bootstrap: CLAUDE.md, conventions.md, working-memory.md created (2026-03-10)

## Open Issues

- #5: Parse Solidity visibility modifiers for reachability (referenced by voro-brain Phase 2.4)

## Blockers

- voro-brain Phase 2.4 re-eval blocked by #5 (visibility modifiers)

## References

- Architecture: `CLAUDE.md`
- Deployment: `docs/DEPLOY_ZEABUR.md`
- API schema: `openapi.json`
