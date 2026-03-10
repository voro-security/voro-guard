#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path


def _extract_title(text: str, fallback: str) -> str:
    m = re.search(r"^#\s*Sprint:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else fallback


def _extract_repos(text: str) -> str:
    m = re.search(r"^#\s*Repos:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else "unknown"


def _extract_prs(text: str) -> str:
    prs = sorted(set(re.findall(r"PR\s*#(\d+)", text)))
    return ", ".join(f"#{p}" for p in prs) if prs else "none"


def _extract_keywords(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z_-]{3,}", text)
    stop = {"task", "this", "that", "with", "from", "into", "then", "none", "repo", "repol", "sprint"}
    out = []
    for w in words:
        lw = w.lower()
        if lw in stop:
            continue
        if lw not in out:
            out.append(lw)
        if len(out) == 12:
            break
    return ", ".join(out) if out else "none"


def update_sprint_file(sprint_file: Path, task: str, pr_number: str, sha: str, what: str, archive_dir: Path, today: str):
    text = sprint_file.read_text(encoding="utf-8")
    if task.strip().upper() == "NONE":
        return {"updated": False, "closed": False, "archived_path": None}

    escaped = re.escape(task.strip())
    pattern = re.compile(rf"^\s*- \[ \]\s+{escaped}\s*$", re.M)
    replacement = f"- [x] {task.strip()} — PR #{pr_number} sha:{sha[:7]}"
    new_text, count = pattern.subn(replacement, text, count=1)
    if count == 0:
        raise ValueError(f"Task not found unchecked in sprint file: {task}")

    all_tasks = re.findall(r"^\s*- \[( |x|X)\]\s+.+$", new_text, re.M)
    all_done = bool(all_tasks) and all(x.lower() == "x" for x in all_tasks)

    if not all_done:
        sprint_file.write_text(new_text, encoding="utf-8")
        return {"updated": True, "closed": False, "archived_path": None}

    title = _extract_title(new_text, sprint_file.stem)
    repos = _extract_repos(new_text)
    prs = _extract_prs(new_text)
    keywords = _extract_keywords(new_text)

    if not re.search(r"^#\s*Status:\s*CLOSED\s*$", new_text, re.M):
        new_text = f"# Status: CLOSED\n{new_text}"

    archive_header = (
        f"# Sprint: {title}\n"
        f"# Closed: {today}\n"
        f"# Repos: {repos}\n"
        f"# PRs: {prs}\n"
        f"# Keywords: {keywords}\n"
        f"# Result: {what.strip()}\n\n"
    )

    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_path = archive_dir / sprint_file.name
    archived_path.write_text(archive_header + new_text, encoding="utf-8")
    sprint_file.unlink()
    return {"updated": True, "closed": True, "archived_path": str(archived_path)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sprint-file", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--pr-number", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--what", required=True)
    ap.add_argument("--archive-dir", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    sf = Path(args.sprint_file)
    if not sf.exists():
        print(f"ERROR: sprint file not found: {sf}", file=sys.stderr)
        return 1
    try:
        res = update_sprint_file(
            sf,
            args.task,
            args.pr_number,
            args.sha,
            args.what,
            Path(args.archive_dir),
            args.date,
        )
    except Exception as exc:
        print(f"ERROR: failed updating sprint: {exc}", file=sys.stderr)
        return 1
    print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
