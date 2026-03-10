# voro-guard Conventions

> Auto-loaded into system prompt. These are non-negotiable rules.

## Architecture Contract

Seven repos. No cross-repo Python imports. JSON over CLI/HTTP/MCP. Period.

- **voro-brain** is the primary consumer — calls via MCP stdio subprocess
- **voro-guard** exposes HTTP REST + MCP stdio, never imported as a Python module
- ArtifactEnvelope is the output contract — do not break its schema

## Trust Model

- **Strict mode** (production): All artifacts must have valid HMAC-SHA256 signature
- **Legacy mode** (dev only): Unsigned artifacts accepted when `CODE_INDEX_TRUST_MODE=legacy`
- Never weaken trust verification logic

## DO NOT

- Import this repo from any other VORO repo — MCP/HTTP only
- Disable artifact signing in production
- Expose signing keys, service tokens, or GitHub PATs in logs or tests
- Add AST parsing — regex extraction is intentional
- Break the MCP stdio contract (voro-brain depends on it)
- Modify ArtifactEnvelope schema without updating voro-brain consumers
- Add cloud logging or external telemetry (local-first)

## Commit Message Template

```
<type>: <imperative, <70 chars>

<why — 1-2 sentences explaining motivation>

<optional: bullet list of notable changes>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

Types: feat, fix, refactor, docs, chore, test

## Anti-Hallucination Protocol (MANDATORY)

Before writing code that calls ANY internal function/class/API:

1. READ the source file first
2. QUOTE the actual signature in your response
3. THEN write the calling code using EXACT parameter names
4. RUN tests immediately after

## On Every Session Start / After Compaction (MANDATORY)

1. This file + `working-memory.md` are already loaded (you're reading them)
2. **Read `CLAUDE.md`** — full architectural reference. This takes seconds and prevents blind exploration.
3. Check `git diff` and `git log --oneline -10`
4. Run `pytest tests/unit/` to verify nothing is broken
5. Resume from working-memory.md current task

**Never skip step 2.**

---

## Sprint Doc Naming Convention (MANDATORY)

All new .md files created in .claude/plans/ must follow this format:

  YYYYMMDD-<repo>-<slug>.md
  Examples:
    20260315-brain-calibration-fp-fix.md
    20260315-scan-oracle-patterns.md
    20260315-web-paywall-gate.md

Repo short names:
  voro-scan     → scan
  voro-brain    → brain
  voro-web      → web
  voro-guard    → guard
  voro-core     → core
  voro-dash     → dash

Rules:
- Date prefix is the creation date in YYYYMMDD format
- Slug is 2-4 lowercase words, hyphen-separated, describing the topic
- Random word names (e.g. zany-booping-shell.md) are never created
- One doc per topic — if a plan exists for this topic, update it in place,
  do not create a parallel version
- Before creating any new plan, grep ~/.claude/archive/ARCHIVE_LOG.md
  to check if this work was already done in a previous session

Every new sprint doc must include this 5-line header at the top:

  # Status: ACTIVE
  # Tier: SPRINT
  # Created: YYYY-MM-DD
  # Repo: <repo-name>
  # Closes: <PR number, issue number, or milestone>

When work is complete, Claude updates Status: ACTIVE → Status: CLOSED.
The Stop hook archives it automatically on the next response.
