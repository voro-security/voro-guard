import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.schemas import GetRequest, IndexRequest, OutlineRequest, SearchRequest
from app.routes.index import create_index
from app.routes.query import get_outline, get_symbol, search_index


def test_index_and_search_local_repo(tmp_path: Path) -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.artifact_root = str(tmp_path / "artifacts")

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "sample.py").write_text(
        "class Wallet:\n"
        "    pass\n\n"
        "def detect_risk(x):\n"
        "    return x\n",
        encoding="utf-8",
    )

    indexed = create_index(
        IndexRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:repo1",
            repo_ref=str(repo),
        )
    )

    payload = indexed["payload"]
    assert payload["stats"]["file_count"] == 1
    assert payload["stats"]["symbol_count"] >= 2

    search = search_index(
        SearchRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:repo1",
            artifact_id=indexed["artifact_id"],
            query="detect_risk",
        )
    )
    assert search["ok"] is True
    assert any(r["name"] == "detect_risk" for r in search["results"])

    symbol_id = next(r["id"] for r in search["results"] if r["name"] == "detect_risk")
    got = get_symbol(
        GetRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:repo1",
            artifact_id=indexed["artifact_id"],
            symbol_id=symbol_id,
        )
    )
    assert got["ok"] is True
    assert got["results"][0]["symbol"]["name"] == "detect_risk"
    assert "snippet" in got["results"][0]["symbol"]
    assert got["results"][0]["file_meta"]["path"] == "sample.py"

    outline = get_outline(
        OutlineRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:repo1",
            artifact_id=indexed["artifact_id"],
        )
    )
    assert outline["ok"] is True
    summary = outline["results"]["summary"]
    assert summary["file_count"] == 1
    assert summary["symbol_count"] >= 2
