import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from app.config import settings
from app.core.artifacts import artifact_path
from app.models.schemas import IndexRequest, QueryRequest
from app.routes.index import create_index
from app.routes.query import get_outline, get_symbol, query_index, search_index
from app.models.schemas import GetRequest, OutlineRequest, SearchRequest


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2), encoding="utf-8")


def setup_function() -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.artifact_root = "/tmp/voro-index-guard-tests"
    root = Path(settings.artifact_root)
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                p.unlink()


def test_missing_artifact_returns_artifact_missing() -> None:
    req = QueryRequest(
        workspace_id="ws1",
        repo_fingerprint="sha256:abc",
        artifact_id="does-not-exist",
        mode="search",
        query="foo",
    )
    try:
        query_index(req)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail["reason_code"] == "artifact_missing"


def test_tampered_artifact_body_returns_hash_mismatch() -> None:
    indexed = create_index(IndexRequest(workspace_id="ws1", repo_fingerprint="sha256:abc"))
    p = Path(indexed["artifact_path"])
    obj = _load_json(p)
    obj["payload"]["repo_ref"] = "tampered"
    _write_json(p, obj)

    req = QueryRequest(
        workspace_id="ws1",
        repo_fingerprint="sha256:abc",
        artifact_id=indexed["artifact_id"],
        mode="search",
        query="foo",
    )
    try:
        query_index(req)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["reason_code"] == "artifact_untrusted_hash_mismatch"


def test_tampered_signature_returns_signature_invalid() -> None:
    indexed = create_index(IndexRequest(workspace_id="ws1", repo_fingerprint="sha256:abc"))
    p = Path(indexed["artifact_path"])
    obj = _load_json(p)
    obj["manifest"]["signature"] = "deadbeef"
    _write_json(p, obj)

    req = QueryRequest(
        workspace_id="ws1",
        repo_fingerprint="sha256:abc",
        artifact_id=indexed["artifact_id"],
        mode="search",
        query="foo",
    )
    try:
        query_index(req)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["reason_code"] == "artifact_untrusted_signature_invalid"


def test_identity_mismatch_returns_identity_mismatch() -> None:
    indexed = create_index(IndexRequest(workspace_id="ws1", repo_fingerprint="sha256:abc"))
    src = Path(indexed["artifact_path"])
    obj = _load_json(src)

    dst = artifact_path("ws2", "sha256:abc", indexed["artifact_id"])
    _write_json(dst, obj)

    req = QueryRequest(
        workspace_id="ws2",
        repo_fingerprint="sha256:abc",
        artifact_id=indexed["artifact_id"],
        mode="search",
        query="foo",
    )
    try:
        query_index(req)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["reason_code"] == "artifact_identity_mismatch"


def test_strict_mode_unsigned_artifact_denied() -> None:
    indexed = create_index(IndexRequest(workspace_id="ws1", repo_fingerprint="sha256:abc"))
    p = Path(indexed["artifact_path"])
    obj = _load_json(p)
    obj["manifest"]["signature"] = ""
    _write_json(p, obj)

    req = QueryRequest(
        workspace_id="ws1",
        repo_fingerprint="sha256:abc",
        artifact_id=indexed["artifact_id"],
        mode="search",
        query="foo",
    )
    try:
        query_index(req)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["reason_code"] == "artifact_untrusted_missing_manifest"


def test_split_routes_search_get_outline_success() -> None:
    indexed = create_index(IndexRequest(workspace_id="ws1", repo_fingerprint="sha256:abc"))

    search_resp = search_index(
        SearchRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:abc",
            artifact_id=indexed["artifact_id"],
            query="foo",
        )
    )
    assert search_resp["ok"] is True
    assert search_resp["mode"] == "search"

    get_resp = get_symbol(
        GetRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:abc",
            artifact_id=indexed["artifact_id"],
            symbol_id="sym-1",
        )
    )
    assert get_resp["ok"] is True
    assert get_resp["mode"] == "get"

    outline_resp = get_outline(
        OutlineRequest(
            workspace_id="ws1",
            repo_fingerprint="sha256:abc",
            artifact_id=indexed["artifact_id"],
        )
    )
    assert outline_resp["ok"] is True
    assert outline_resp["mode"] == "outline"
