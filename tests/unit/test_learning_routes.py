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
