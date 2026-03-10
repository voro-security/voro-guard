from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_sprint


def test_update_single_task(tmp_path: Path):
    sp = tmp_path / "s.md"
    sp.write_text("# Sprint: S1\n# Repos: voro-scan\n\n- [ ] Task A\n- [ ] Task B\n")
    res = update_sprint.update_sprint_file(sp, "Task A", "1", "abcdef1", "done", tmp_path / "archive", "2026-03-10")
    assert res["updated"] is True
    assert res["closed"] is False
    assert "- [x] Task A — PR #1 sha:abcdef1" in sp.read_text()


def test_all_done_archives(tmp_path: Path):
    sp = tmp_path / "s.md"
    sp.write_text("# Sprint: S1\n# Repos: voro-scan\n\n- [ ] Task A\n")
    arch = tmp_path / "archive"
    res = update_sprint.update_sprint_file(sp, "Task A", "9", "abcdef1", "Result line", arch, "2026-03-10")
    assert res["closed"] is True
    assert not sp.exists()
    ap = arch / "s.md"
    assert ap.exists()
    txt = ap.read_text()
    assert "# Status: CLOSED" in txt
    assert "# Result: Result line" in txt
