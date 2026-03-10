from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import update_status


def test_happy_path(tmp_path: Path):
    status = tmp_path / "STATUS.md"
    update_status.update_status(status, "Did thing", "Task A", "Task B", "123", "abcdef123", "2026-03-10")
    txt = status.read_text()
    assert "# STATUS" in txt
    assert "| 2026-03-10 | #123 | abcdef1 | Did thing |" in txt
    assert "- Task B" in txt


def test_none_values(tmp_path: Path):
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## In Progress\n- Task A\n\n## Next\n\n## Done\n| Date | PR | SHA | Summary |\n|------|----|-----|---------|\n")
    update_status.update_status(status, "Done", "NONE", "NONE", "2", "1234567", "2026-03-10")
    txt = status.read_text()
    assert "| 2026-03-10 | #2 | 1234567 | Done |" in txt
    assert "- Task A" in txt


def test_fuzzy_removes_from_in_progress(tmp_path: Path):
    """Task with different casing/whitespace still removes from In Progress."""
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## In Progress\n- Fix the  login   bug\n\n## Next\n\n## Done\n| Date | PR | SHA | Summary |\n|------|----|-----|---------|\n")
    update_status.update_status(status, "Fixed it", "fix THE login bug", "NONE", "5", "abc1234", "2026-03-10")
    txt = status.read_text()
    assert "Fix the  login   bug" not in txt
    assert "| 2026-03-10 | #5 |" in txt


def test_fuzzy_removes_from_next(tmp_path: Path):
    """Completing a task also removes its matching entry from Next."""
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## In Progress\n\n## Next\n- Remove SMOKE_TEST.md after verifying workflow runs.\n\n## Done\n| Date | PR | SHA | Summary |\n|------|----|-----|---------|\n")
    update_status.update_status(status, "Cleaned up", "Remove SMOKE_TEST.md after verifying workflow runs.", "NONE", "6", "def5678", "2026-03-10")
    txt = status.read_text()
    assert "SMOKE_TEST" not in txt
    assert "| 2026-03-10 | #6 |" in txt


def test_fuzzy_next_dedup(tmp_path: Path):
    """Adding to Next with different whitespace/case doesn't create duplicate."""
    status = tmp_path / "STATUS.md"
    status.write_text("# STATUS\n\n## In Progress\n\n## Next\n- Deploy to production\n\n## Done\n| Date | PR | SHA | Summary |\n|------|----|-----|---------|\n")
    update_status.update_status(status, "Prepped", "NONE", "deploy  TO  production", "7", "aaa1111", "2026-03-10")
    txt = status.read_text()
    # Should not have a duplicate entry
    assert txt.count("production") == 1
