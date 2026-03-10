#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

AUTO_START = "<!--AUTO-START-->"
AUTO_END = "<!--AUTO-END-->"
REPO_ORDER = ["voro-scan", "voro-brain", "voro-web", "voro-guard", "voro-core", "voro-dash"]


def parse_status(path: Path):
    txt = path.read_text(encoding="utf-8") if path.exists() else ""
    in_prog = "—"
    m = re.search(r"## In Progress\n(.*?)\n## Next\n", txt, re.S)
    if m:
        lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
        if lines:
            in_prog = lines[0]
    last_pr = "—"
    done = re.search(r"## Done\n(.*)$", txt, re.S)
    if done:
        rows = [ln for ln in done.group(1).splitlines() if ln.strip().startswith("|") and "---" not in ln and " Date " not in ln]
        if rows:
            cols = [c.strip() for c in rows[-1].strip("|").split("|")]
            if len(cols) >= 2:
                last_pr = f"{cols[0]} {cols[1]}"
    return in_prog, last_pr


def parse_sprint(path: Path):
    txt = path.read_text(encoding="utf-8")
    title = re.search(r"^#\s*Sprint:\s*(.+)$", txt, re.M)
    repos = re.search(r"^#\s*Repos:\s*(.+)$", txt, re.M)
    task_lines = re.findall(r"^\s*- \[( |x|X)\]\s+.+$", txt, re.M)
    total = len(task_lines)
    done = sum(1 for t in task_lines if t.lower() == "x")
    return {
        "sprint": title.group(1).strip() if title else path.name,
        "repos": repos.group(1).strip() if repos else "unknown",
        "progress": f"{done}/{total}",
        "doc": f"sprints/{path.name}",
    }


def rebuild(master_file: Path, status_dir: Path, sprints_dir: Path):
    text = master_file.read_text(encoding="utf-8")
    if AUTO_START not in text or AUTO_END not in text:
        raise ValueError("AUTO markers not found in VORO_MASTER.md")

    sprint_files = [p for p in sorted(sprints_dir.glob("*.md")) if p.name != ".gitkeep"]
    sprint_rows = []
    for sf in sprint_files:
        s = parse_sprint(sf)
        sprint_rows.append(f"| {s['sprint']} | {s['repos']} | {s['progress']} | [{sf.name}]({s['doc']}) |")
    if not sprint_rows:
        sprint_rows = ["| _(none yet)_ | — | — | — |"]

    fleet_rows = []
    for repo in REPO_ORDER:
        status_file = status_dir / f"{repo}.md"
        in_prog, last_pr = parse_status(status_file)
        fleet_rows.append(f"| {repo} | {in_prog} | {last_pr} |")

    auto_block = "\n".join([
        AUTO_START,
        "## Active Sprints",
        "",
        "| Sprint | Repos | Progress | Doc |",
        "|--------|-------|----------|-----|",
        *sprint_rows,
        "",
        "## Fleet Status",
        "",
        "| Repo | In Progress | Last PR |",
        "|------|-------------|---------|",
        *fleet_rows,
        AUTO_END,
    ])

    new_text = re.sub(
        re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END),
        auto_block,
        text,
        flags=re.S,
    )
    master_file.write_text(new_text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status-dir", required=True)
    ap.add_argument("--sprints-dir", required=True)
    ap.add_argument("--master-file", required=True)
    args = ap.parse_args()
    try:
        rebuild(Path(args.master_file), Path(args.status_dir), Path(args.sprints_dir))
    except Exception as exc:
        print(f"ERROR: aggregate failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
