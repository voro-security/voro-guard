from pathlib import Path
import sys

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
    settings.adaptive_learning_enabled = True


def test_governance_report_read_and_list_routes(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")

    publish = client.post(
        "/v1/learning-state",
        json={
            "workspace_id": "voro",
            "source_id": "github-governance",
            "state_type": "governance-report",
            "payload": {
                "schema_version": "github-governance-drift-report-v1",
                "status": "PASS",
                "repo_count": 8,
            },
            "metadata": {"published_at": "2026-03-16T20:00:00Z"},
        },
    )
    assert publish.status_code == 200
    published = publish.json()

    read = client.get(
        "/v1/governance-report",
        params={"workspace_id": "voro"},
    )
    assert read.status_code == 200
    read_body = read.json()
    assert read_body["artifact_id"] == published["artifact_id"]
    assert read_body["payload"]["state_type"] == "governance-report"
    assert read_body["source_id"] == "github-governance"

    listed = client.get(
        "/v1/governance-reports",
        params={"workspace_id": "voro"},
    )
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["count"] == 1
    assert listed_body["items"][0]["artifact_id"] == published["artifact_id"]
    assert listed_body["items"][0]["state_type"] == "governance-report"


def test_governance_report_read_404_when_missing(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")

    response = client.get(
        "/v1/governance-report",
        params={"workspace_id": "voro"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["reason_code"] == "artifact_missing"
