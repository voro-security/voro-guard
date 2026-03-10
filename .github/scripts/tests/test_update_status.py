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
