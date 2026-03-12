#!/usr/bin/env python3
"""Validate the minimum VORO docs contract for this repo."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]

README_SECTIONS = [
    "## What This Repo Is",
    "## Quick Start",
    "## Run",
    "## Test",
    "## Fleet Role",
    "## Key Paths",
    "## Documentation",
]

CLAUDE_MARKERS = [
    "## Identity",
    "## Architecture Role",
    "## Validation",
    "## Guardrails",
    "## Session Start",
    "## Cross-Repo Awareness",
    "## Architectural Reference",
]

STATUS_SECTIONS = [
    "# STATUS",
    "## In Progress",
    "## Next",
    "## Done",
]

CODEBASE_MAP_HEADERS = [
    "# Status:",
    "# Class:",
    "# Authority:",
    "# Generator:",
    "# Generated At:",
    "# Source Revision:",
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"missing required file: {path.relative_to(ROOT)}")


def require_markers(path: Path, markers: list[str]) -> list[str]:
    content = read_text(path)
    missing = [marker for marker in markers if marker not in content]
    return [f"{path.relative_to(ROOT)} missing: {marker}" for marker in missing]


def main() -> int:
    errors: list[str] = []
    errors.extend(require_markers(ROOT / "README.md", README_SECTIONS))
    errors.extend(require_markers(ROOT / "CLAUDE.md", CLAUDE_MARKERS))
    errors.extend(require_markers(ROOT / "STATUS.md", STATUS_SECTIONS))
    errors.extend(require_markers(ROOT / "docs" / "CODEBASE_MAP.md", CODEBASE_MAP_HEADERS))

    if errors:
        for error in errors:
            print(error)
        return 1

    print("docs contract validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
