#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path


def _normalize_task_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^- \[[ xX]\]\s*", "", s)
    s = re.sub(r"^-\s*", "", s)
    return s.strip()


def _fuzzy(s: str) -> str:
    """Whitespace-normalized, case-insensitive key for comparison."""
    return re.sub(r"\s+", " ", s.strip()).lower()


def _canonical_status() -> str:
    return """# STATUS

## In Progress

## Next

## Done
| Date | PR | SHA | Summary |
|------|----|-----|---------|
"""


def _split_sections(text: str):
    text = text.replace("\r\n", "\n")
    if "## In Progress" not in text or "## Next" not in text or "## Done" not in text:
        text = _canonical_status()
    m = re.search(r"## In Progress\n(.*?)\n## Next\n(.*?)\n## Done\n(.*)", text, re.S)
    if not m:
        text = _canonical_status()
        m = re.search(r"## In Progress\n(.*?)\n## Next\n(.*?)\n## Done\n(.*)", text, re.S)
    assert m is not None
    return m.group(1).strip("\n"), m.group(2).strip("\n"), m.group(3).strip("\n")


def update_status(status_file: Path, what: str, task: str, whats_next: str, pr_number: str, sha: str, date_str: str) -> None:
    existing = status_file.read_text(encoding="utf-8") if status_file.exists() else ""
    in_progress, next_sec, done_sec = _split_sections(existing)

    in_progress_lines = [ln for ln in in_progress.splitlines() if ln.strip()]
    next_lines = [ln for ln in next_sec.splitlines() if ln.strip()]

    if task.strip().upper() != "NONE":
        task_key = _fuzzy(task)
        in_progress_lines = [ln for ln in in_progress_lines if _fuzzy(_normalize_task_line(ln)) != task_key]
        next_lines = [ln for ln in next_lines if _fuzzy(_normalize_task_line(ln)) != task_key]

    if whats_next.strip().upper() != "NONE":
        if _fuzzy(whats_next) not in [_fuzzy(_normalize_task_line(x)) for x in next_lines]:
            next_lines.append(f"- {whats_next.strip()}")

    done_lines = done_sec.splitlines()
    if not done_lines:
        done_lines = ["| Date | PR | SHA | Summary |", "|------|----|-----|---------|"]
    if not any("| Date | PR | SHA | Summary |" in ln for ln in done_lines):
        done_lines.insert(0, "| Date | PR | SHA | Summary |")
        done_lines.insert(1, "|------|----|-----|---------|")

    short_sha = sha[:7]
    row = f"| {date_str} | #{pr_number} | {short_sha} | {what.strip()} |"
    done_lines.append(row)

    out = [
        "# STATUS",
        "",
        "## In Progress",
        *(in_progress_lines or [""]),
        "",
        "## Next",
        *(next_lines or [""]),
        "",
        "## Done",
        *done_lines,
        "",
    ]
    status_file.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status-file", required=True)
    ap.add_argument("--what", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--next", dest="whats_next", required=True)
    ap.add_argument("--pr-number", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    try:
        update_status(
            Path(args.status_file),
            args.what,
            args.task,
            args.whats_next,
            args.pr_number,
            args.sha,
            args.date,
        )
    except Exception as exc:
        print(f"ERROR: failed updating STATUS.md: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
