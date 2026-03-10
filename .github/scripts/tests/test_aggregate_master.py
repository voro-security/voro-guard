from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aggregate_master


def test_marker_boundary(tmp_path: Path):
    master = tmp_path / "VORO_MASTER.md"
    master.write_text("HEAD\n<!--AUTO-START-->\nold\n<!--AUTO-END-->\n\nHUMAN-SECTION\n")

    status_dir = tmp_path / "status"
    status_dir.mkdir()
    for r in ["voro-scan", "voro-brain", "voro-web", "voro-guard", "voro-core", "voro-dash"]:
        (status_dir / f"{r}.md").write_text("# STATUS\n\n## In Progress\n\n## Next\n\n## Done\n| Date | PR | SHA | Summary |\n|------|----|-----|---------|\n")

    sprints = tmp_path / "sprints"
    sprints.mkdir()

    aggregate_master.rebuild(master, status_dir, sprints)
    txt = master.read_text()
    assert "HUMAN-SECTION" in txt
    assert "## Fleet Status" in txt
    assert txt.startswith("HEAD\n")
