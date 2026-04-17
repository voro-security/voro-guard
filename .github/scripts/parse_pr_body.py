#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List

REQUIRED_FIELDS = [
    "What this does",
    "Sprint this belongs to",
    "Task this completes",
    "What's next",
    "Breaking changes",
]


def parse_pr_body(body: str, pr_title: str = "") -> Dict[str, str]:
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body or ""))
    values: Dict[str, str] = {}
    warnings: List[str] = []

    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if heading in REQUIRED_FIELDS:
            values[heading] = content if content else "NONE"

    missing = [f for f in REQUIRED_FIELDS if f not in values]
    if missing:
        warnings.append(f"Missing PR template fields: {', '.join(missing)}")

    what_this_does = values.get("What this does", "").strip()
    if not what_this_does:
        fallback = pr_title.strip()
        if fallback:
            what_this_does = fallback
            warnings.append("Fell back to PR title for 'What this does'")
        else:
            what_this_does = "Merged PR"
            warnings.append("Used generic fallback for 'What this does'")

    normalized = {
        "what_this_does": what_this_does,
        "sprint": values.get("Sprint this belongs to", "NONE"),
        "task": values.get("Task this completes", "NONE"),
        "whats_next": values.get("What's next", "NONE"),
        "breaking_changes": values.get("Breaking changes", "NONE"),
        "warnings": warnings,
    }
    return normalized


def main() -> int:
    body = os.environ.get("PR_BODY", "")
    pr_title = os.environ.get("PR_TITLE", "")
    if not body and len(sys.argv) > 1:
        body = sys.argv[1]
    if not body and not pr_title:
        print("ERROR: PR body/title are empty (set PR_BODY, PR_TITLE, or pass body as arg)", file=sys.stderr)
        return 2
    try:
        result = parse_pr_body(body, pr_title=pr_title)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
