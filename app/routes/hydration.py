"""Hydration plane — session resume protocol.

Reuses existing learning-state signed artifact infrastructure.
State types: system-state, repo-state, work-state.
hydrate_session assembles them with freshness calculation.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from app.routes.learning import (
    _load_learning_state_candidates,
    _verify_learning_artifact,
    publish_learning_state,
)
from app.models.schemas import LearningStatePublishRequest
from app.security import require_auth

router = APIRouter()

HYDRATION_STATE_TYPES = {"system-state", "repo-state", "work-state"}

# Freshness thresholds (hours) per spec Section 4
_FRESHNESS_THRESHOLDS = {
    "system-state": {"fresh": 24, "stale": 72},
    "repo-state": {"fresh": 4, "stale": 24},
    "work-state": {"fresh": 2, "stale": 8},
}

# Work-state expiry (days) per spec Section 7
_WORK_STATE_EXPIRY_DAYS = 7


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Ensure timezone-aware (naive timestamps treated as UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _freshness_for(state_type: str, signed_at: str | None) -> str:
    ts = _parse_timestamp(signed_at)
    if ts is None:
        return "degraded"
    now = datetime.now(timezone.utc)
    age_hours = (now - ts).total_seconds() / 3600
    thresholds = _FRESHNESS_THRESHOLDS.get(state_type, {"fresh": 24, "stale": 72})
    if age_hours <= thresholds["fresh"]:
        return "fresh"
    if age_hours <= thresholds["stale"]:
        return "stale"
    return "degraded"


def _worst_freshness(statuses: list[str]) -> str:
    if "degraded" in statuses:
        return "degraded"
    if "stale" in statuses:
        return "stale"
    return "fresh"


def _extract_state_payload(artifact: dict[str, Any]) -> dict[str, Any] | None:
    payload = artifact.get("payload", {})
    inner = payload.get("payload")
    if isinstance(inner, dict):
        return inner
    return payload


def _filter_work_state(
    candidates: list[dict[str, Any]],
    agent_id: str | None,
    repo: str | None,
    worktree_path: str | None,
    workspace_root: str | None = None,
) -> dict[str, Any] | None:
    """Find the best matching work-state by identity key.

    Identity key per spec Section 6: (workspace_root, repo, worktree_path, agent_id).
    All four fields are filtered when provided.
    """
    for artifact in candidates:
        payload = artifact.get("payload", {})
        state = payload.get("payload", payload)
        if not isinstance(state, dict):
            continue
        if state.get("schema_version") != "work-state-v1":
            continue
        if agent_id and state.get("agent_id") != agent_id:
            continue
        if repo and state.get("repo") != repo:
            continue
        if worktree_path and state.get("worktree_path") != worktree_path:
            continue
        if workspace_root and state.get("workspace_root") != workspace_root:
            continue
        # Check expiry
        updated = _parse_timestamp(
            state.get("updated_at")
            or artifact.get("manifest", {}).get("signed_at")
        )
        if updated:
            age_days = (datetime.now(timezone.utc) - updated).total_seconds() / 86400
            if age_days > _WORK_STATE_EXPIRY_DAYS:
                return {**state, "_expired": True}
        return state
    return None


@router.get("/v1/hydrate")
def hydrate_session(
    workspace_id: str = Query(min_length=1),
    agent_id: str | None = None,
    repo: str | None = None,
    worktree_path: str | None = None,
    workspace_root: str | None = None,
    authorization: str | None = Header(default=None),
):
    """Assemble a hydration response from stored state artifacts.

    Returns system-state, matching repo-states, and the best matching
    work-state with freshness calculation. Not a stored artifact —
    computed on each call.
    """
    require_auth(authorization)

    try:
        candidates = _load_learning_state_candidates(workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason_code": str(exc), "message": str(exc)},
        ) from exc

    # Classify candidates by state type
    system_state: dict[str, Any] | None = None
    repo_states: list[dict[str, Any]] = []
    work_candidates: list[dict[str, Any]] = []
    freshness_statuses: list[str] = []
    warnings: list[str] = []

    for artifact in candidates:
        artifact_id = str(artifact.get("artifact_id", ""))
        ok, reason = _verify_learning_artifact(artifact, workspace_id, artifact_id)
        if not ok:
            warnings.append(f"untrusted artifact skipped: {artifact_id} ({reason})")
            continue

        payload = artifact.get("payload", {})
        state_type = payload.get("state_type", "")
        signed_at = artifact.get("manifest", {}).get("signed_at")

        if state_type == "system-state":
            state = _extract_state_payload(artifact)
            if state and (system_state is None):
                freshness = _freshness_for("system-state", signed_at)
                freshness_statuses.append(freshness)
                if freshness != "fresh":
                    warnings.append(f"system-state is {freshness} (signed {signed_at})")
                system_state = state

        elif state_type == "repo-state":
            state = _extract_state_payload(artifact)
            if state:
                state_repo = state.get("repo", "")
                if repo is None or state_repo == repo:
                    freshness = _freshness_for("repo-state", signed_at)
                    freshness_statuses.append(freshness)
                    if freshness != "fresh":
                        warnings.append(f"repo-state for {state_repo} is {freshness}")
                    repo_states.append(state)

        elif state_type == "work-state":
            work_candidates.append(artifact)

    # Find best matching work-state
    work_state = _filter_work_state(work_candidates, agent_id, repo, worktree_path, workspace_root)
    if work_state:
        if work_state.get("_expired"):
            warnings.append("work-state is expired (>7 days without update)")
            freshness_statuses.append("degraded")
            work_state.pop("_expired", None)
        else:
            updated = work_state.get("updated_at")
            freshness = _freshness_for("work-state", updated)
            freshness_statuses.append(freshness)
            if freshness != "fresh":
                warnings.append(f"work-state is {freshness} (updated {updated})")

    # Assemble read_next pointers
    read_next: list[str] = []
    if system_state:
        refs = system_state.get("authoritative_refs", [])
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict):
                    path = ref.get("path", "")
                elif isinstance(ref, str):
                    path = ref
                else:
                    continue
                if path:
                    read_next.append(path)

    if not system_state:
        warnings.append("no system-state available — read EXECUTION_CONTRACT.md directly")
    if not repo_states:
        warnings.append("no repo-state available — run git status locally")
    if not work_state:
        warnings.append("no work-state available — read working-memory.md for context")

    overall_freshness = _worst_freshness(freshness_statuses) if freshness_statuses else "degraded"

    return {
        "ok": True,
        "schema_version": "hydration-response-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freshness_status": overall_freshness,
        "freshness_warnings": warnings if warnings else None,
        "system_state": system_state,
        "repo_states": repo_states,
        "work_state": work_state,
        "read_next": read_next if read_next else None,
        "warnings": warnings if warnings else None,
    }
