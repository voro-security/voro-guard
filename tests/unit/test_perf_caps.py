import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.core.indexer import build_payload_from_repo


def test_indexing_respects_file_cap(tmp_path: Path) -> None:
    repo = tmp_path / "big-repo"
    repo.mkdir(parents=True, exist_ok=True)

    for i in range(12):
        (repo / f"m{i}.py").write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")

    old_max_files = settings.max_files
    old_timeout = settings.index_timeout_seconds
    try:
        settings.max_files = 5
        settings.index_timeout_seconds = 30
        payload = build_payload_from_repo(str(repo))
    finally:
        settings.max_files = old_max_files
        settings.index_timeout_seconds = old_timeout

    assert payload["stats"]["file_count"] <= 5
    assert payload["stats"]["symbol_count"] <= 5

