import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.service_token = ""
    settings.adaptive_learning_enabled = False


def test_learning_routes_disabled_return_404(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")

    publish = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "voro-brain",
            "state_type": "priors",
            "payload": {"alpha": 0.7},
            "metadata": {},
        },
    )
    assert publish.status_code == 404
    assert publish.json()["reason"] == "adaptive_learning_disabled"

    read = client.get("/v1/learning-state/some-artifact", params={"workspace_id": "ws1"})
    assert read.status_code == 404
    assert read.json()["reason"] == "adaptive_learning_disabled"

    listed = client.get("/v1/learning-states", params={"workspace_id": "ws1"})
    assert listed.status_code == 404
    assert listed.json()["reason"] == "adaptive_learning_disabled"


def test_publish_read_and_list_learning_state_flow(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    publish = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "voro-brain",
            "state_type": "priors",
            "payload": {"alpha": 0.7, "beta": 1.3},
            "metadata": {"published_at": "2026-03-14T00:00:00Z"},
        },
    )
    assert publish.status_code == 200
    published = publish.json()
    assert published["ok"] is True
    assert published["schema_version"] == "learning-v1"
    assert published["source_type"] == "learning_state"
    assert published["source_id"] == "voro-brain"
    assert published["payload"]["state_type"] == "priors"
    assert published["payload"]["metadata"]["published_at"] == "2026-03-14T00:00:00Z"
    assert published["payload"]["payload"] == {"alpha": 0.7, "beta": 1.3}

    read = client.get(
        f"/v1/learning-state/{published['artifact_id']}",
        params={"workspace_id": "ws1"},
    )
    assert read.status_code == 200
    read_body = read.json()
    assert read_body["ok"] is True
    assert read_body["artifact_id"] == published["artifact_id"]
    assert read_body["artifact_version"] == 1

    listed = client.get(
        "/v1/learning-states",
        params={"workspace_id": "ws1", "source_id": "voro-brain", "state_type": "priors"},
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["count"] == 1
    assert listed_body["items"][0]["artifact_id"] == published["artifact_id"]
    assert listed_body["items"][0]["state_type"] == "priors"
    assert listed_body["items"][0]["source_id"] == "voro-brain"


def test_list_learning_states_handles_workspace_ids_with_colon(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    publish = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws:1",
            "source_id": "voro-brain",
            "state_type": "priors",
            "payload": {"alpha": 0.7},
            "metadata": {"published_at": "2026-03-14T00:00:00Z"},
        },
    )
    assert publish.status_code == 200

    listed = client.get("/v1/learning-states", params={"workspace_id": "ws:1"})
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["count"] == 1
    assert listed_body["items"][0]["source_id"] == "voro-brain"


def test_publish_learning_state_invalid_workspace_returns_4xx(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws/1",
            "source_id": "voro-brain",
            "state_type": "priors",
            "payload": {"alpha": 0.7},
            "metadata": {},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"


def test_read_learning_state_invalid_workspace_returns_4xx(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.get(
        "/v1/learning-state/art-1",
        params={"workspace_id": "ws/1"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"


def test_list_learning_states_invalid_workspace_returns_4xx(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.get("/v1/learning-states", params={"workspace_id": "ws/1"})
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"


def test_publish_learning_state_requires_signing_key_in_strict_mode(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")
    settings.signing_key = ""

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "voro-brain",
            "state_type": "priors",
            "payload": {"alpha": 0.7},
            "metadata": {},
        },
    )
    assert response.status_code == 500
    assert response.json()["detail"]["reason_code"] == "internal_error"


def test_publish_valid_work_state_payload_is_accepted(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "work-state:claude-code:voro-guard:test123",
            "state_type": "work-state",
            "payload": {
                "schema_version": "work-state-v1",
                "agent_id": "claude_code",
                "workspace_root": "/home/user/dev/voro",
                "repo": "voro-guard",
                "worktree_path": "/home/user/dev/voro/voro-guard",
                "updated_at": "2026-03-18T22:55:23Z",
                "current_objective": "Verify compaction work-state publish path",
                "open_loops": ["Resume hydration validation."],
                "do_not_redo": ["Do not replace local fallback."],
                "relevant_refs": ["/home/user/.claude/VORO_STARTUP.md"],
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["payload"]
    assert payload["schema_version"] == "work-state-v1"
    assert payload["agent_id"] == "claude_code"
    assert payload["repo"] == "voro-guard"


def test_publish_invalid_work_state_payload_is_rejected(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "work-state:claude-code:voro-guard:test123",
            "state_type": "work-state",
            "payload": {
                "schema_version": "work-state-v1",
                "agent_id": "claude_code",
                "workspace_root": "/home/user/dev/voro",
                "repo": "voro-guard",
                "updated_at": "2026-03-18T22:55:23Z",
                "current_objective": "Missing required worktree path",
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"


def test_publish_valid_system_state_payload_is_accepted(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "fleet",
            "state_type": "system-state",
            "payload": {
                "schema_version": "system-state-v1",
                "generated_at": "2026-03-18T22:55:23Z",
                "contract_path": "/home/user/dev/voro/voro-docs/EXECUTION_CONTRACT.md",
                "current_phase_focus": ["1", "2C"],
                "phase_statuses": [{"phase": "2C", "status": "active"}],
                "current_blockers": ["none"],
                "next_recommended_lane": "Phase 2C hydration slice",
                "authoritative_refs": [
                    {"path": "EXECUTION_CONTRACT.md", "role": "governing"},
                    {"path": "docs/hydration-plane-spec.md", "role": "binding"},
                ],
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["payload"]
    assert payload["schema_version"] == "system-state-v1"
    assert payload["next_recommended_lane"] == "Phase 2C hydration slice"
    assert payload["authoritative_refs"][0]["role"] == "governing"


def test_publish_invalid_system_state_payload_is_rejected(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "fleet",
            "state_type": "system-state",
            "payload": {
                "schema_version": "system-state-v1",
                "generated_at": "2026-03-18T22:55:23Z",
                "current_phase_focus": ["1", "2C"],
                "phase_statuses": [{"phase": "2C", "status": "active"}],
                "current_blockers": ["none"],
                "next_recommended_lane": "Phase 2C hydration slice",
                "authoritative_refs": [{"path": "EXECUTION_CONTRACT.md"}],
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"


def test_publish_valid_repo_state_payload_is_accepted(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "voro-guard",
            "state_type": "repo-state",
            "payload": {
                "schema_version": "repo-state-v1",
                "repo": "voro-guard",
                "captured_at": "2026-03-18T22:55:23Z",
                "branch": "feat/hydration",
                "head_sha": "abc1234",
                "dirty": False,
                "important_boundaries": ["app/routes/hydration.py"],
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["payload"]
    assert payload["schema_version"] == "repo-state-v1"
    assert payload["repo"] == "voro-guard"
    assert payload["dirty"] is False


def test_publish_invalid_repo_state_payload_is_rejected(tmp_path: Path) -> None:
    settings.adaptive_learning_enabled = True
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "ws1",
            "source_id": "voro-guard",
            "state_type": "repo-state",
            "payload": {
                "schema_version": "repo-state-v1",
                "repo": "voro-guard",
                "captured_at": "2026-03-18T22:55:23Z",
                "branch": "feat/hydration",
                "dirty": False,
            },
            "metadata": {"published_at": "2026-03-18T22:55:23Z"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["reason_code"] == "artifact_invalid"
