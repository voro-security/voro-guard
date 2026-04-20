"""
Unit tests for voro_mcp.mcp_server.

All HTTP calls are mocked — the FastAPI server does NOT need to be running.
Tests cover:
  - search_symbols proxies to /v1/search
  - get_symbol proxies to /v1/get
  - outline_file proxies to /v1/outline
  - index_repo proxies to /v1/index
  - index_docs proxies to /v1/index with docs mode
  - search_docs proxies to /v1/search with optional visibility
  - get_doc_section proxies to /v1/get with doc_id or section_id
  - outline_docs proxies to /v1/outline with optional visibility
  - publish_learning_state proxies to /v1/learning-state
  - read_learning_state proxies to GET /v1/learning-state/{artifact_id}
  - list_learning_states proxies to GET /v1/learning-states with optional filters
  - source_fingerprint is forwarded when provided
  - optional fields are omitted from request body when empty
  - HTTP 4xx errors are converted to RuntimeError with reason_code
  - transport errors are converted to RuntimeError
  - auth header is added when INDEX_GUARD_TOKEN is set
  - auth header is absent when INDEX_GUARD_TOKEN is empty
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Ensure repo root is on sys.path.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(status: int, body: dict, url: str = "http://127.0.0.1:18765/v1/search") -> httpx.Response:
    """Build a mock httpx.Response with the given status and JSON body."""
    request = httpx.Request("POST", url)
    return httpx.Response(status_code=status, json=body, request=request)


def _mock_post(response: httpx.Response):
    """Return a context-manager patch that makes httpx.post return *response*."""
    return patch("httpx.post", return_value=response)


def _mock_post_raises(exc: Exception):
    """Return a context-manager patch that makes httpx.post raise *exc*."""
    return patch("httpx.post", side_effect=exc)


def _mock_get(response: httpx.Response):
    """Return a context-manager patch that makes httpx.get return *response*."""
    return patch("httpx.get", return_value=response)


# ---------------------------------------------------------------------------
# search_symbols
# ---------------------------------------------------------------------------


def test_search_symbols_proxies_to_v1_search():
    """search_symbols posts to /v1/search and returns the JSON response."""
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": [{"name": "do_stuff"}]}
    with _mock_post(_make_response(200, expected)) as mock:
        result = mod.search_symbols(
            query="do_stuff",
            workspace_id="ws1",
            artifact_id="art1",
        )
    mock.assert_called_once()
    call_kwargs = mock.call_args
    assert "/v1/search" in call_kwargs.args[0]
    body = call_kwargs.kwargs["json"]
    assert body["query"] == "do_stuff"
    assert body["workspace_id"] == "ws1"
    assert body["artifact_id"] == "art1"
    assert result == expected


def test_search_symbols_includes_source_fingerprint_when_provided():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
        mod.search_symbols(
            query="foo",
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="sha256:deadbeef",
        )
    body = mock.call_args.kwargs["json"]
    assert body["source_fingerprint"] == "sha256:deadbeef"


def test_search_symbols_omits_source_fingerprint_when_empty():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
        mod.search_symbols(
            query="foo",
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="",
        )
    body = mock.call_args.kwargs["json"]
    assert "source_fingerprint" not in body


# ---------------------------------------------------------------------------
# get_symbol
# ---------------------------------------------------------------------------


def test_get_symbol_proxies_to_v1_get():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": [{"symbol": {"id": "sym-1"}}]}
    with _mock_post(_make_response(200, expected)) as mock:
        result = mod.get_symbol(
            symbol_id="sym-1",
            workspace_id="ws1",
            artifact_id="art1",
        )
    call_kwargs = mock.call_args
    assert "/v1/get" in call_kwargs.args[0]
    body = call_kwargs.kwargs["json"]
    assert body["symbol_id"] == "sym-1"
    assert result == expected


def test_get_symbol_includes_source_fingerprint_when_provided():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
        mod.get_symbol(
            symbol_id="sym-2",
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="sha256:abc123",
        )
    body = mock.call_args.kwargs["json"]
    assert body["source_fingerprint"] == "sha256:abc123"


# ---------------------------------------------------------------------------
# outline_file
# ---------------------------------------------------------------------------


def test_outline_file_proxies_to_v1_outline():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": {"files": []}}
    with _mock_post(_make_response(200, expected)) as mock:
        result = mod.outline_file(
            workspace_id="ws1",
            artifact_id="art1",
        )
    call_kwargs = mock.call_args
    assert "/v1/outline" in call_kwargs.args[0]
    body = call_kwargs.kwargs["json"]
    assert body["workspace_id"] == "ws1"
    assert body["artifact_id"] == "art1"
    assert result == expected


def test_outline_file_includes_source_fingerprint_when_provided():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": {}})) as mock:
        mod.outline_file(
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="sha256:fp1",
        )
    body = mock.call_args.kwargs["json"]
    assert body["source_fingerprint"] == "sha256:fp1"


# ---------------------------------------------------------------------------
# index_repo
# ---------------------------------------------------------------------------


def test_index_repo_proxies_to_v1_index():
    import voro_mcp.mcp_server as mod

    expected = {
        "ok": True,
        "artifact_id": "abcdef123456",
        "source_fingerprint": "sha256:fp99",
    }
    with _mock_post(_make_response(200, expected)) as mock:
        result = mod.index_repo(
            source_type="github",
            source_id="owner/repo",
            workspace_id="ws1",
        )
    call_kwargs = mock.call_args
    assert "/v1/index" in call_kwargs.args[0]
    body = call_kwargs.kwargs["json"]
    assert body["source_type"] == "github"
    assert body["source_id"] == "owner/repo"
    assert body["workspace_id"] == "ws1"
    assert "source_revision" not in body
    assert result == expected


def test_index_repo_includes_source_revision_when_provided():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True})) as mock:
        mod.index_repo(
            source_type="github",
            source_id="owner/repo",
            workspace_id="ws1",
            source_revision="abc123",
        )
    body = mock.call_args.kwargs["json"]
    assert body["source_revision"] == "abc123"


def test_index_repo_omits_source_revision_when_empty():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True})) as mock:
        mod.index_repo(
            source_type="local_repo",
            source_id="/home/user/myrepo",
            workspace_id="ws1",
            source_revision="",
        )
    body = mock.call_args.kwargs["json"]
    assert "source_revision" not in body


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_http_4xx_raises_runtime_error_with_reason_code():
    import voro_mcp.mcp_server as mod

    error_body = {"reason_code": "artifact_missing", "message": "not found"}
    mock_resp = _make_response(404, error_body)
    # httpx.HTTPStatusError requires a request object
    request = httpx.Request("POST", "http://127.0.0.1:18765/v1/search")
    exc = httpx.HTTPStatusError("404", request=request, response=mock_resp)

    with _mock_post_raises(exc):
        with pytest.raises(RuntimeError) as exc_info:
            mod.search_symbols(query="foo", workspace_id="ws1", artifact_id="art1")
    assert "artifact_missing" in str(exc_info.value)
    assert "404" in str(exc_info.value)


def test_http_5xx_raises_runtime_error():
    import voro_mcp.mcp_server as mod

    error_body = {"reason_code": "internal_error", "message": "boom"}
    mock_resp = _make_response(500, error_body)
    request = httpx.Request("POST", "http://127.0.0.1:18765/v1/search")
    exc = httpx.HTTPStatusError("500", request=request, response=mock_resp)

    with _mock_post_raises(exc):
        with pytest.raises(RuntimeError) as exc_info:
            mod.search_symbols(query="bar", workspace_id="ws1", artifact_id="art1")
    assert "internal_error" in str(exc_info.value)


def test_transport_error_raises_runtime_error():
    import voro_mcp.mcp_server as mod

    with _mock_post_raises(httpx.ConnectError("connection refused")):
        with pytest.raises(RuntimeError) as exc_info:
            mod.get_symbol(symbol_id="x", workspace_id="ws1", artifact_id="art1")
    assert "unreachable" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Docs tools
# ---------------------------------------------------------------------------


def test_index_docs_proxies_to_v1_index_with_docs_mode():
    import voro_mcp.mcp_server as mod

    expected = {
        "ok": True,
        "artifact_id": "docs-artifact-1",
        "source_fingerprint": "sha256:docs",
    }
    with _mock_post(_make_response(200, expected, url="http://127.0.0.1:18765/v1/index")) as mock:
        result = mod.index_docs(
            source_type="local_repo",
            source_id="/repo",
            workspace_id="ws1",
            source_revision="r1",
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/index" in mock.call_args.args[0]
    assert body["index_kind"] == "docs"
    assert body["source_type"] == "local_repo"
    assert body["source_id"] == "/repo"
    assert body["source_revision"] == "r1"
    assert result == expected


def test_search_docs_proxies_to_v1_search_with_visibility():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": [{"section_id": "sec-1"}]}
    with _mock_post(_make_response(200, expected)) as mock:
        result = mod.search_docs(
            query="intro",
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="sha256:docs",
            allowed_visibility=["public", "pro"],
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/search" in mock.call_args.args[0]
    assert body["query"] == "intro"
    assert body["source_fingerprint"] == "sha256:docs"
    assert body["allowed_visibility"] == ["public", "pro"]
    assert result == expected


def test_search_docs_omits_optional_fields_when_empty():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
        mod.search_docs(
            query="intro",
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="",
            allowed_visibility=None,
        )
    body = mock.call_args.kwargs["json"]
    assert "source_fingerprint" not in body
    assert "allowed_visibility" not in body


def test_get_doc_section_proxies_to_v1_get_by_doc_id():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": [{"document": {"doc_id": "doc-1"}}]}
    with _mock_post(_make_response(200, expected, url="http://127.0.0.1:18765/v1/get")) as mock:
        result = mod.get_doc_section(
            workspace_id="ws1",
            artifact_id="art1",
            doc_id="doc-1",
            source_fingerprint="sha256:docs",
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/get" in mock.call_args.args[0]
    assert body["doc_id"] == "doc-1"
    assert body["source_fingerprint"] == "sha256:docs"
    assert "section_id" not in body
    assert result == expected


def test_get_doc_section_proxies_to_v1_get_by_section_id_with_visibility():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": []}, url="http://127.0.0.1:18765/v1/get")) as mock:
        mod.get_doc_section(
            workspace_id="ws1",
            artifact_id="art1",
            section_id="sec-1",
            allowed_visibility=["enterprise"],
        )
    body = mock.call_args.kwargs["json"]
    assert body["section_id"] == "sec-1"
    assert body["allowed_visibility"] == ["enterprise"]
    assert "doc_id" not in body


def test_get_doc_section_requires_doc_id_or_section_id():
    import voro_mcp.mcp_server as mod

    with pytest.raises(ValueError) as exc_info:
        mod.get_doc_section(
            workspace_id="ws1",
            artifact_id="art1",
        )
    assert "doc_id_or_section_id_required" in str(exc_info.value)


def test_outline_docs_proxies_to_v1_outline_with_visibility():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "results": {"documents": []}}
    with _mock_post(_make_response(200, expected, url="http://127.0.0.1:18765/v1/outline")) as mock:
        result = mod.outline_docs(
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="sha256:docs",
            allowed_visibility=["public", "pro"],
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/outline" in mock.call_args.args[0]
    assert body["workspace_id"] == "ws1"
    assert body["artifact_id"] == "art1"
    assert body["source_fingerprint"] == "sha256:docs"
    assert body["allowed_visibility"] == ["public", "pro"]
    assert result == expected


def test_outline_docs_omits_optional_fields_when_empty():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True, "results": {"documents": []}}, url="http://127.0.0.1:18765/v1/outline")) as mock:
        mod.outline_docs(
            workspace_id="ws1",
            artifact_id="art1",
            source_fingerprint="",
            allowed_visibility=None,
        )
    body = mock.call_args.kwargs["json"]
    assert "source_fingerprint" not in body
    assert "allowed_visibility" not in body


# ---------------------------------------------------------------------------
# Learning tools
# ---------------------------------------------------------------------------


def test_publish_learning_state_proxies_to_learning_state_post():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "artifact_id": "learning-1"}
    with _mock_post(_make_response(200, expected, url="http://127.0.0.1:18765/v1/learning-state")) as mock:
        result = mod.publish_learning_state(
            workspace_id="ws1",
            source_id="voro-brain",
            state_type="priors",
            payload={"alpha": 0.7},
            metadata={"published_at": "2026-03-14T00:00:00Z"},
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/learning-state" in mock.call_args.args[0]
    assert body["workspace_id"] == "ws1"
    assert body["source_id"] == "voro-brain"
    assert body["state_type"] == "priors"
    assert body["payload"] == {"alpha": 0.7}
    assert body["metadata"] == {"published_at": "2026-03-14T00:00:00Z"}
    assert result == expected


def test_publish_learning_state_omits_empty_metadata():
    import voro_mcp.mcp_server as mod

    with _mock_post(_make_response(200, {"ok": True}, url="http://127.0.0.1:18765/v1/learning-state")) as mock:
        mod.publish_learning_state(
            workspace_id="ws1",
            source_id="voro-scan",
            state_type="precision",
            payload={"fp_rate": 0.1},
            metadata=None,
        )
    body = mock.call_args.kwargs["json"]
    assert "metadata" not in body


def test_publish_work_state_proxies_to_learning_state_post():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "artifact_id": "learning-1"}
    with _mock_post(_make_response(200, expected, url="http://127.0.0.1:18765/v1/learning-state")) as mock:
        result = mod.publish_work_state(
            workspace_id="ws1",
            current_objective="Resume compaction recovery work",
            agent_id="Claude Code",
            workspace_root="/home/user/dev/voro",
            repo="voro-guard",
            worktree_path="/home/user/dev/voro/voro-guard",
            open_loops=["Re-run hydration verification"],
            do_not_redo=["Do not replace fallback continuity"],
            relevant_refs=["/home/user/.claude/VORO_STARTUP.md"],
        )
    body = mock.call_args.kwargs["json"]
    assert "/v1/learning-state" in mock.call_args.args[0]
    assert body["workspace_id"] == "ws1"
    assert body["state_type"] == "work-state"
    assert body["source_id"].startswith("work-state:claude-code:voro-guard:")
    assert body["payload"]["schema_version"] == "work-state-v1"
    assert body["payload"]["agent_id"] == "Claude Code"
    assert body["payload"]["current_objective"] == "Resume compaction recovery work"
    assert result == expected


def test_read_learning_state_proxies_to_learning_state_get():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "schema_version": "learning-v1"}
    with _mock_get(_make_response(200, expected, url="http://127.0.0.1:18765/v1/learning-state/art-1")) as mock:
        result = mod.read_learning_state(workspace_id="ws1", artifact_id="art-1")
    assert "/v1/learning-state/art-1" in mock.call_args.args[0]
    params = mock.call_args.kwargs["params"]
    assert params == {"workspace_id": "ws1"}
    assert result == expected


def test_list_learning_states_proxies_to_learning_states_get_with_filters():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "items": []}
    with _mock_get(_make_response(200, expected, url="http://127.0.0.1:18765/v1/learning-states")) as mock:
        result = mod.list_learning_states(
            workspace_id="ws1",
            source_id="voro-brain",
            state_type="quarantine",
            limit=25,
        )
    assert "/v1/learning-states" in mock.call_args.args[0]
    params = mock.call_args.kwargs["params"]
    assert params["workspace_id"] == "ws1"
    assert params["source_id"] == "voro-brain"
    assert params["state_type"] == "quarantine"
    assert params["limit"] == 25
    assert result == expected


def test_list_learning_states_omits_empty_filters():
    import voro_mcp.mcp_server as mod

    with _mock_get(_make_response(200, {"ok": True, "items": []}, url="http://127.0.0.1:18765/v1/learning-states")) as mock:
        mod.list_learning_states(workspace_id="ws1")
    params = mock.call_args.kwargs["params"]
    assert params == {"workspace_id": "ws1", "limit": 100}


def test_read_governance_report_proxies_to_governance_report_get():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "schema_version": "learning-v1"}
    with _mock_get(_make_response(200, expected, url="http://127.0.0.1:18765/v1/governance-report")) as mock:
        result = mod.read_governance_report(workspace_id="voro")
    assert "/v1/governance-report" in mock.call_args.args[0]
    params = mock.call_args.kwargs["params"]
    assert params == {"workspace_id": "voro", "source_id": "github-governance"}
    assert result == expected


def test_list_governance_reports_proxies_to_governance_reports_get():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "items": []}
    with _mock_get(_make_response(200, expected, url="http://127.0.0.1:18765/v1/governance-reports")) as mock:
        result = mod.list_governance_reports(workspace_id="voro", limit=10)
    assert "/v1/governance-reports" in mock.call_args.args[0]
    params = mock.call_args.kwargs["params"]
    assert params == {"workspace_id": "voro", "source_id": "github-governance", "limit": 10}
    assert result == expected


def test_hydrate_session_proxies_full_identity_filters():
    import voro_mcp.mcp_server as mod

    expected = {"ok": True, "schema_version": "hydration-response-v1"}
    with _mock_get(_make_response(200, expected, url="http://127.0.0.1:18765/v1/hydrate")) as mock:
        result = mod.hydrate_session(
            workspace_id="ws1",
            agent_id="claude_1",
            repo="voro-guard",
            worktree_path="/home/user/dev/voro/voro-guard",
            workspace_root="/home/user/dev/voro",
        )
    assert "/v1/hydrate" in mock.call_args.args[0]
    params = mock.call_args.kwargs["params"]
    assert params == {
        "workspace_id": "ws1",
        "agent_id": "claude_1",
        "repo": "voro-guard",
        "worktree_path": "/home/user/dev/voro/voro-guard",
        "workspace_root": "/home/user/dev/voro",
    }
    assert result == expected


def test_hydrate_session_end_to_end_uses_workspace_root_filter(tmp_path: Path):
    import voro_mcp.mcp_server as mod
    from voro_mcp.config import settings
    from voro_mcp.models.schemas import LearningStatePublishRequest
    from voro_mcp.routes.learning import publish_learning_state
    from voro_mcp.main import app
    from fastapi.testclient import TestClient

    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.adaptive_learning_enabled = True
    settings.service_token = ""
    settings.artifact_root = str(tmp_path / "artifacts")

    ws = "mcp-hydrate-ws"
    common_state = {
        "schema_version": "work-state-v1",
        "agent_id": "claude_1",
        "repo": "voro-guard",
        "updated_at": "2026-04-01T12:00:00Z",
        "current_objective": "hydration objective",
    }

    publish_learning_state(
        LearningStatePublishRequest(
            workspace_id=ws,
            source_id="work-state:claude-1:voro-guard:a",
            state_type="work-state",
            payload={
                **common_state,
                "workspace_root": "/workspace-a",
                "worktree_path": "/workspace-a/voro-guard",
            },
            metadata={"published_at": "2026-04-01T12:00:00Z"},
        ),
        authorization=None,
    )
    publish_learning_state(
        LearningStatePublishRequest(
            workspace_id=ws,
            source_id="work-state:claude-1:voro-guard:b",
            state_type="work-state",
            payload={
                **common_state,
                "workspace_root": "/workspace-b",
                "worktree_path": "/workspace-b/voro-guard",
                "current_objective": "workspace b objective",
            },
            metadata={"published_at": "2026-04-01T12:00:00Z"},
        ),
        authorization=None,
    )

    client = TestClient(app)

    def _route_get(url: str, *, params=None, headers=None, timeout=None):
        path = url.removeprefix(mod.INDEX_GUARD_URL)
        response = client.get(path, params=params, headers=headers)
        return httpx.Response(
            status_code=response.status_code,
            json=response.json(),
            request=httpx.Request("GET", url),
        )

    with patch("httpx.get", side_effect=_route_get):
        result = mod.hydrate_session(
            workspace_id=ws,
            agent_id="claude_1",
            repo="voro-guard",
            workspace_root="/workspace-b",
        )

    assert result["ok"] is True
    assert result["work_state"] is not None
    assert result["work_state"]["workspace_root"] == "/workspace-b"
    assert result["work_state"]["current_objective"] == "workspace b objective"
# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


def test_auth_header_added_when_token_set():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    try:
        mod.INDEX_GUARD_TOKEN = "my-secret-token"
        with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
            mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        headers = mock.call_args.kwargs["headers"]
        assert headers.get("Authorization") == "Bearer my-secret-token"
    finally:
        mod.INDEX_GUARD_TOKEN = original_token


def test_auth_header_absent_when_no_token():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    original_url = mod.INDEX_GUARD_URL
    try:
        mod.INDEX_GUARD_TOKEN = ""
        mod.INDEX_GUARD_URL = "https://guard.example.com"
        with patch.object(mod, "_recover_token_from_local_guard_process", return_value="") as recover_mock:
            with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
                mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        headers = mock.call_args.kwargs["headers"]
        assert "Authorization" not in headers
        recover_mock.assert_called_once()
    finally:
        mod.INDEX_GUARD_TOKEN = original_token
        mod.INDEX_GUARD_URL = original_url


def test_auth_header_recovers_token_from_local_guard_process():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    original_url = mod.INDEX_GUARD_URL
    try:
        mod.INDEX_GUARD_TOKEN = ""
        mod.INDEX_GUARD_URL = "http://127.0.0.1:18765"
        with patch.object(mod, "_recover_token_from_local_guard_process", return_value="proc-token") as recover_mock:
            with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
                mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        headers = mock.call_args.kwargs["headers"]
        assert headers.get("Authorization") == "Bearer proc-token"
        recover_mock.assert_called_once()
        assert mod.INDEX_GUARD_TOKEN == "proc-token"
    finally:
        mod.INDEX_GUARD_TOKEN = original_token
        mod.INDEX_GUARD_URL = original_url


def test_auth_header_does_not_recover_token_for_remote_guard_url():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    original_url = mod.INDEX_GUARD_URL
    try:
        mod.INDEX_GUARD_TOKEN = ""
        mod.INDEX_GUARD_URL = "https://guard.example.com"
        with patch.object(mod, "_recover_token_from_local_guard_process", return_value="") as recover_mock:
            with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
                mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        headers = mock.call_args.kwargs["headers"]
        assert "Authorization" not in headers
        recover_mock.assert_called_once()
    finally:
        mod.INDEX_GUARD_TOKEN = original_token
        mod.INDEX_GUARD_URL = original_url


def test_auth_header_does_not_recover_token_for_local_non_managed_port():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    original_url = mod.INDEX_GUARD_URL
    try:
        mod.INDEX_GUARD_TOKEN = ""
        mod.INDEX_GUARD_URL = "http://127.0.0.1:8080"
        with patch.object(mod, "_recover_token_from_local_guard_process", return_value="") as recover_mock:
            with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
                mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        headers = mock.call_args.kwargs["headers"]
        assert "Authorization" not in headers
        recover_mock.assert_called_once()
    finally:
        mod.INDEX_GUARD_TOKEN = original_token
        mod.INDEX_GUARD_URL = original_url


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def test_base_url_used_for_all_tools():
    """All tools POST to INDEX_GUARD_URL, not a hardcoded host."""
    import voro_mcp.mcp_server as mod

    original_url = mod.INDEX_GUARD_URL
    try:
        mod.INDEX_GUARD_URL = "http://custom-host:9999"
        with _mock_post(_make_response(200, {"ok": True, "results": []})) as mock:
            mod.search_symbols(query="x", workspace_id="ws1", artifact_id="art1")
        assert mock.call_args.args[0].startswith("http://custom-host:9999")
    finally:
        mod.INDEX_GUARD_URL = original_url


def test_managed_artifact_root_defaults_to_user_state_dir(monkeypatch):
    import voro_mcp.mcp_server as mod

    monkeypatch.delenv("VORO_MCP_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

    assert mod._default_managed_artifact_root() == "/tmp/xdg-state/voro-mcp/artifacts"


def test_start_managed_server_sets_artifact_root_when_missing(monkeypatch):
    import voro_mcp.mcp_server as mod

    monkeypatch.delenv("ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(mod, "_managed_proc", None)
    monkeypatch.setattr(mod, "_STARTUP_TIMEOUT", 1)
    monkeypatch.setattr(mod, "_MANAGED_PORT", 18765)
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")

    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.wait = MagicMock()

    ready = MagicMock(status_code=200)

    with patch("subprocess.Popen", return_value=proc) as popen_mock, patch("httpx.get", return_value=ready):
        mod._start_managed_server()

    env = popen_mock.call_args.kwargs["env"]
    assert env["ARTIFACT_ROOT"] == "/tmp/xdg-state/voro-mcp/artifacts"
    assert "voro_mcp.main:app" in popen_mock.call_args.args[0]
    mod._managed_proc = None


def test_load_repo_local_env_extracts_missing_index_guard_vars():
    import voro_mcp.mcp_server as mod

    stdout = (
        b"CODE_INDEX_SIGNING_KEY=sign-key\0"
        b"CODE_INDEX_SERVICE_TOKEN=svc-token\0"
        b"UNRELATED=value\0"
    )
    completed = MagicMock(stdout=stdout)
    with patch.object(mod, "_repo_root", return_value=Path("/tmp/repo")):
        with patch("pathlib.Path.is_file", return_value=True):
            with patch.dict(mod.os.environ, {}, clear=True):
                with patch("subprocess.run", return_value=completed) as run_mock:
                    loaded = mod._load_repo_local_env()
    run_mock.assert_called_once()
    assert loaded == {
        "CODE_INDEX_SIGNING_KEY": "sign-key",
        "CODE_INDEX_SERVICE_TOKEN": "svc-token",
    }


def test_start_managed_server_updates_token_from_repo_local_env():
    import voro_mcp.mcp_server as mod

    original_token = mod.INDEX_GUARD_TOKEN
    original_proc = mod._managed_proc
    proc = MagicMock()
    try:
        mod.INDEX_GUARD_TOKEN = ""
        mod._managed_proc = None
        with patch.object(mod, "_load_repo_local_env", return_value={"CODE_INDEX_SERVICE_TOKEN": "repo-token"}):
            with patch("subprocess.Popen", return_value=proc) as popen_mock:
                with patch("httpx.get", return_value=httpx.Response(200, json={"status": "ok"})):
                    mod._start_managed_server()
        env = popen_mock.call_args.kwargs["env"]
        assert env["CODE_INDEX_SERVICE_TOKEN"] == "repo-token"
        assert mod.INDEX_GUARD_TOKEN == "repo-token"
    finally:
        mod.INDEX_GUARD_TOKEN = original_token
        mod._managed_proc = original_proc
