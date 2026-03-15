"""Tests for the hydration plane — session resume protocol."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.schemas import LearningStatePublishRequest
from app.routes.learning import publish_learning_state
from app.routes.hydration import (
    hydrate_session,
    _freshness_for,
    _worst_freshness,
)


def setup_function() -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.adaptive_learning_enabled = True
    settings.service_token = ""  # disable auth for unit tests


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish_state(tmp_path: Path, workspace_id: str, source_id: str, state_type: str, payload: dict) -> dict:
    settings.artifact_root = str(tmp_path / "artifacts")
    return publish_learning_state(
        LearningStatePublishRequest(
            workspace_id=workspace_id,
            source_id=source_id,
            state_type=state_type,
            payload=payload,
            metadata={"published_at": _now_iso()},
        ),
        authorization=None,
    )


# --- Freshness calculation ---


def test_freshness_fresh():
    now = datetime.now(timezone.utc).isoformat()
    assert _freshness_for("system-state", now) == "fresh"
    assert _freshness_for("repo-state", now) == "fresh"
    assert _freshness_for("work-state", now) == "fresh"


def test_freshness_stale():
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    assert _freshness_for("system-state", old) == "stale"
    old_repo = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    assert _freshness_for("repo-state", old_repo) == "stale"
    old_work = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    assert _freshness_for("work-state", old_work) == "stale"


def test_freshness_degraded():
    very_old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    assert _freshness_for("system-state", very_old) == "degraded"
    assert _freshness_for("repo-state", very_old) == "degraded"
    assert _freshness_for("work-state", very_old) == "degraded"


def test_freshness_none():
    assert _freshness_for("system-state", None) == "degraded"


def test_worst_freshness():
    assert _worst_freshness(["fresh", "fresh"]) == "fresh"
    assert _worst_freshness(["fresh", "stale"]) == "stale"
    assert _worst_freshness(["fresh", "degraded"]) == "degraded"
    assert _worst_freshness(["stale", "degraded"]) == "degraded"
    assert _worst_freshness([]) == "fresh"


# --- Hydration with no state ---


def test_hydrate_empty_workspace(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")
    result = hydrate_session(workspace_id="empty-ws")
    assert result["ok"] is True
    assert result["schema_version"] == "hydration-response-v1"
    assert result["freshness_status"] == "degraded"
    assert result["system_state"] is None
    assert result["repo_states"] == []
    assert result["work_state"] is None
    assert any("no system-state" in w for w in result["warnings"])
    assert any("no repo-state" in w for w in result["warnings"])
    assert any("no work-state" in w for w in result["warnings"])


# --- Hydration with published state ---


def test_hydrate_with_system_and_repo_state(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "test-ws"

    # Publish system-state
    _publish_state(tmp_path, ws, "fleet", "system-state", {
        "schema_version": "system-state-v1",
        "generated_at": _now_iso(),
        "contract_path": "/dev/voro/voro-docs/EXECUTION_CONTRACT.md",
        "current_phase_focus": ["1", "1.5"],
        "phase_statuses": [{"phase": "1", "status": "open"}],
        "current_blockers": ["Phase 1 evidence"],
        "next_recommended_lane": "Phase 1 evidence collection",
        "authoritative_refs": [{"path": "EXECUTION_CONTRACT.md", "role": "governing"}],
    })

    # Publish repo-state
    _publish_state(tmp_path, ws, "voro-brain", "repo-state", {
        "schema_version": "repo-state-v1",
        "repo": "voro-brain",
        "captured_at": _now_iso(),
        "branch": "main",
        "head_sha": "c4cae72",
        "dirty": False,
    })

    result = hydrate_session(workspace_id=ws)
    assert result["ok"] is True
    assert result["freshness_status"] == "fresh"
    assert result["system_state"] is not None
    assert result["system_state"]["current_phase_focus"] == ["1", "1.5"]
    assert len(result["repo_states"]) == 1
    assert result["repo_states"][0]["repo"] == "voro-brain"
    assert result["work_state"] is None


def test_hydrate_with_work_state_filtering(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "test-ws"

    # Publish work-state for agent claude_1 in voro-brain
    _publish_state(tmp_path, ws, "claude_1-voro-brain", "work-state", {
        "schema_version": "work-state-v1",
        "agent_id": "claude_1",
        "workspace_root": "/home/user/dev/voro",
        "repo": "voro-brain",
        "worktree_path": "/home/user/dev/voro/voro-brain",
        "updated_at": _now_iso(),
        "current_objective": "Phase 1 evidence collection",
    })

    # Publish work-state for agent codex_1 in voro-scan
    _publish_state(tmp_path, ws, "codex_1-voro-scan", "work-state", {
        "schema_version": "work-state-v1",
        "agent_id": "codex_1",
        "workspace_root": "/home/user/dev/voro",
        "repo": "voro-scan",
        "worktree_path": "/home/user/dev/voro/voro-scan",
        "updated_at": _now_iso(),
        "current_objective": "Overnight tuning pipeline",
    })

    # Hydrate for claude_1 in voro-brain — should get only that work-state
    result = hydrate_session(workspace_id=ws, agent_id="claude_1", repo="voro-brain")
    assert result["ok"] is True
    assert result["work_state"] is not None
    assert result["work_state"]["agent_id"] == "claude_1"
    assert result["work_state"]["repo"] == "voro-brain"

    # Hydrate for codex_1 in voro-scan — should get only that work-state
    result2 = hydrate_session(workspace_id=ws, agent_id="codex_1", repo="voro-scan")
    assert result2["work_state"] is not None
    assert result2["work_state"]["agent_id"] == "codex_1"

    # Hydrate for unknown agent — should get no work-state
    result3 = hydrate_session(workspace_id=ws, agent_id="gemini_1")
    assert result3["work_state"] is None


def test_hydrate_degraded_warns_on_missing_states(tmp_path: Path) -> None:
    settings.artifact_root = str(tmp_path / "artifacts")
    result = hydrate_session(workspace_id="empty-ws")
    assert result["freshness_status"] == "degraded"
    warnings = result.get("warnings", [])
    assert any("no system-state" in w for w in warnings)
    assert any("no repo-state" in w for w in warnings)
    assert any("no work-state" in w for w in warnings)


# --- Integration: system-state publisher → hydrate round-trip ---


def test_hydrate_with_real_system_state_payload(tmp_path: Path) -> None:
    """Publish a system-state.v1 payload via publish_learning_state(),
    then verify hydrate_session() returns it with freshness_status 'fresh'.

    This validates the Phase 2C Slice 2 contract: a real publisher
    populates system-state, and hydration returns actual fleet state
    instead of 'degraded' with 'no system-state available' warnings.
    """
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "integration-ws"

    # Simulate what publish_system_state.py would POST
    system_state_payload = {
        "schema_version": "system-state-v1",
        "generated_at": _now_iso(),
        "contract_path": "/home/user/dev/voro/voro-docs/EXECUTION_CONTRACT.md",
        "current_phase_focus": ["1", "1.5"],
        "phase_statuses": [
            {"phase": "1", "title": "Infra Repair", "status": "open",
             "reason": "Phase 1 evidence gate still open"},
            {"phase": "1.5", "title": "Memory Unification", "status": "active",
             "reason": "Execution override allows parallel"},
        ],
        "current_blockers": ["Phase 1 evidence state missing"],
        "next_recommended_lane": "Phase 1 evidence collection",
        "follow_on_cleanup_lanes": [
            "voro-docs registry/entitlements compatibility-path removal lane",
        ],
        "authoritative_refs": [
            {"path": "EXECUTION_CONTRACT.md", "role": "governing"},
            {"path": "features/feature-infra-repair.md", "role": "supporting"},
        ],
    }

    # Publish via the same endpoint the publisher script uses
    pub_result = _publish_state(
        tmp_path, ws, "fleet", "system-state", system_state_payload
    )
    assert pub_result.get("ok") is True

    # Hydrate and verify system-state is returned fresh
    result = hydrate_session(workspace_id=ws)
    assert result["ok"] is True
    assert result["freshness_status"] == "fresh"
    assert result["system_state"] is not None

    # Verify the hydrated system-state has the published fields
    ss = result["system_state"]
    assert ss["schema_version"] == "system-state-v1"
    assert ss["current_phase_focus"] == ["1", "1.5"]
    assert len(ss["phase_statuses"]) == 2
    assert ss["current_blockers"] == ["Phase 1 evidence state missing"]
    assert ss["next_recommended_lane"] == "Phase 1 evidence collection"
    assert ss["authoritative_refs"][0]["role"] == "governing"

    # No "no system-state available" warning
    warnings = result.get("warnings") or []
    assert not any("no system-state" in w for w in warnings)

    # read_next should contain authoritative ref paths
    read_next = result.get("read_next") or []
    assert "EXECUTION_CONTRACT.md" in read_next


# --- Integration: work-state publisher → hydrate round-trip ---


def _make_work_state(
    agent_id: str,
    repo: str,
    worktree_path: str,
    objective: str,
    *,
    workspace_root: str = "/home/user/dev/voro",
    updated_at: str | None = None,
) -> dict:
    """Build a work-state.v1 payload matching publish_work_state.py output."""
    return {
        "schema_version": "work-state-v1",
        "agent_id": agent_id,
        "workspace_root": workspace_root,
        "repo": repo,
        "worktree_path": worktree_path,
        "updated_at": updated_at or _now_iso(),
        "current_objective": objective,
    }


def test_hydrate_returns_correct_work_state_by_identity(tmp_path: Path) -> None:
    """Hydration returns the correct work-state for the requested identity key.

    Publishes two work-states with different identity keys (same repo,
    different worktrees) and verifies hydration returns the right one.
    """
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "identity-ws"

    # Agent in main worktree
    main_state = _make_work_state(
        "claude_1", "voro-brain", "/home/user/dev/voro/voro-brain",
        "Phase 1 evidence collection",
    )
    _publish_state(tmp_path, ws, "claude_1-voro-brain", "work-state", main_state)

    # Same agent in a feature worktree
    feat_state = _make_work_state(
        "claude_1", "voro-brain", "/tmp/worktree-feat-hydration",
        "Phase 2C hydration slice 3",
    )
    _publish_state(tmp_path, ws, "claude_1-voro-brain-feat", "work-state", feat_state)

    # Request main worktree — should get main objective
    result = hydrate_session(
        workspace_id=ws, agent_id="claude_1", repo="voro-brain",
        worktree_path="/home/user/dev/voro/voro-brain",
    )
    assert result["work_state"] is not None
    assert result["work_state"]["current_objective"] == "Phase 1 evidence collection"
    assert result["work_state"]["worktree_path"] == "/home/user/dev/voro/voro-brain"

    # Request feature worktree — should get feature objective
    result2 = hydrate_session(
        workspace_id=ws, agent_id="claude_1", repo="voro-brain",
        worktree_path="/tmp/worktree-feat-hydration",
    )
    assert result2["work_state"] is not None
    assert result2["work_state"]["current_objective"] == "Phase 2C hydration slice 3"


def test_hydrate_stale_work_state_warns(tmp_path: Path) -> None:
    """A work-state older than 2 hours is stale; hydration warns."""
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "stale-ws"

    stale_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    stale_state = _make_work_state(
        "claude_1", "voro-brain", "/home/user/dev/voro/voro-brain",
        "stale objective", updated_at=stale_time,
    )
    _publish_state(tmp_path, ws, "claude_1-voro-brain", "work-state", stale_state)

    result = hydrate_session(workspace_id=ws, agent_id="claude_1", repo="voro-brain")
    assert result["work_state"] is not None
    assert result["work_state"]["current_objective"] == "stale objective"
    # Overall freshness should reflect staleness
    assert result["freshness_status"] in ("stale", "degraded")
    warnings = result.get("warnings") or []
    assert any("work-state" in w and "stale" in w for w in warnings)


def test_hydrate_expired_work_state_degrades(tmp_path: Path) -> None:
    """A work-state >7 days old is expired; hydration degrades."""
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "expired-ws"

    expired_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    expired_state = _make_work_state(
        "claude_1", "voro-brain", "/home/user/dev/voro/voro-brain",
        "ancient objective", updated_at=expired_time,
    )
    _publish_state(tmp_path, ws, "claude_1-voro-brain", "work-state", expired_state)

    result = hydrate_session(workspace_id=ws, agent_id="claude_1", repo="voro-brain")
    assert result["work_state"] is not None
    assert result["freshness_status"] == "degraded"
    warnings = result.get("warnings") or []
    assert any("expired" in w for w in warnings)


def test_hydrate_missing_work_state_degrades_gracefully(tmp_path: Path) -> None:
    """When no work-state matches the identity, hydration degrades gracefully."""
    settings.artifact_root = str(tmp_path / "artifacts")
    ws = "no-work-ws"

    # Publish a work-state for a different agent
    other_state = _make_work_state(
        "codex_1", "voro-scan", "/home/user/dev/voro/voro-scan",
        "unrelated work",
    )
    _publish_state(tmp_path, ws, "codex_1-voro-scan", "work-state", other_state)

    # Request for claude_1 in voro-brain — no match
    result = hydrate_session(workspace_id=ws, agent_id="claude_1", repo="voro-brain")
    assert result["work_state"] is None
    warnings = result.get("warnings") or []
    assert any("no work-state" in w for w in warnings)
