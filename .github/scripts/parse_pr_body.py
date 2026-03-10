#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict

REQUIRED_FIELDS = [
    "What this does",
    "Sprint this belongs to",
    "Task this completes",
    "What's next",
    "Breaking changes",
]


def parse_pr_body(body: str) -> Dict[str, str]:
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(body or ""))
    values: Dict[str, str] = {}

    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if heading in REQUIRED_FIELDS:
            values[heading] = content if content else "NONE"

    missing = [f for f in REQUIRED_FIELDS if f not in values]
    if missing:
        raise ValueError(f"Missing required PR template fields: {', '.join(missing)}")

    normalized = {
        "what_this_does": values["What this does"],
        "sprint": values["Sprint this belongs to"],
        "task": values["Task this completes"],
        "whats_next": values["What's next"],
        "breaking_changes": values["Breaking changes"],
    }
    return normalized


def main() -> int:
    body = os.environ.get("PR_BODY", "")
    if not body and len(sys.argv) > 1:
        body = sys.argv[1]
    if not body:
        print("ERROR: PR body is empty (set PR_BODY or pass as arg)", file=sys.stderr)
        return 2
    try:
        result = parse_pr_body(body)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
