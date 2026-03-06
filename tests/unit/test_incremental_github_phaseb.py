import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.schemas import IndexRequest
from app.routes.index import create_index
import app.core.indexer as indexer


def test_github_incremental_reuses_unchanged_files(tmp_path: Path, monkeypatch) -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.artifact_root = str(tmp_path / "artifacts")

    trees = [
        [
            {"type": "blob", "path": "a.py", "size": 30, "sha": "sha-a-1"},
            {"type": "blob", "path": "b.py", "size": 30, "sha": "sha-b-1"},
        ],
        [
            {"type": "blob", "path": "a.py", "size": 30, "sha": "sha-a-1"},
            {"type": "blob", "path": "b.py", "size": 30, "sha": "sha-b-2"},
        ],
    ]
    tree_idx = {"i": 0}

    def fake_tree(_owner: str, _repo: str):
        i = tree_idx["i"]
        tree_idx["i"] += 1
        return trees[min(i, len(trees) - 1)]

    fetched_paths: list[str] = []

    def fake_content(_owner: str, _repo: str, file_path: str):
        fetched_paths.append(file_path)
        if file_path == "a.py":
            return "def alpha():\n    return 1\n"
        return "def beta():\n    return 2\n"

    monkeypatch.setattr(indexer, "_fetch_github_tree", fake_tree)
    monkeypatch.setattr(indexer, "_fetch_github_content", fake_content)

    first = create_index(
        IndexRequest(
            workspace_id="ws1",
            source_type="github",
            source_id="owner/repo",
            source_revision="rev-1",
            repo_ref="owner/repo",
        )
    )
    assert first["rebuild_reason"] == "full_rebuild_first_index"
    assert first["artifact_version"] == 1
    assert sorted(fetched_paths) == ["a.py", "b.py"]

    fetched_paths.clear()
    second = create_index(
        IndexRequest(
            workspace_id="ws1",
            source_type="github",
            source_id="owner/repo",
            source_revision="rev-2",
            repo_ref="owner/repo",
        )
    )

    assert second["artifact_id"] == first["artifact_id"]
    assert second["artifact_version"] == 2
    assert second["rebuild_reason"] == "incremental_changed_files"
    assert fetched_paths == ["b.py"]
    incremental_meta = second["payload"]["index_meta"]["incremental"]
    assert incremental_meta["changed_count"] == 1
    assert incremental_meta["reused_count"] == 1
