from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.artifacts import load_latest_artifact, persist_artifact, verify_artifact, _sanitize_component
from app.core.identity import compute_source_fingerprint
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.models.schemas import ArtifactEnvelope, LearningStatePublishRequest, Manifest
from app.security import require_auth


router = APIRouter()
_REASON_STATUS = {
    "artifact_invalid": 422,
    "artifact_path_outside_root": 403,
}
GOVERNANCE_REPORT_SOURCE_ID = "github-governance"
GOVERNANCE_REPORT_STATE_TYPE = "governance-report"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _disabled_response() -> JSONResponse | None:
    if not settings.adaptive_learning_enabled:
        return JSONResponse(status_code=404, content={"reason": "adaptive_learning_disabled"})
    return None


def _learning_revision(metadata: dict[str, Any]) -> str:
    for key in ("source_revision", "state_revision", "published_at", "version"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _now_utc()


def _learning_artifact_id(workspace_id: str, source_id: str, state_type: str) -> str:
    return sha256_hex(f"{workspace_id}:learning_state:{source_id}:{state_type}")[:24]


def _learning_payload(req: LearningStatePublishRequest) -> dict[str, Any]:
    return {
        "state_type": req.state_type,
        "metadata": req.metadata,
        "payload": req.payload,
    }


def _http_error_for_artifact_error(code: str) -> HTTPException:
    status = _REASON_STATUS.get(code, 422)
    return HTTPException(status_code=status, detail={"reason_code": code, "message": code})


def _load_learning_state_candidates(workspace_id: str) -> list[dict[str, Any]]:
    ws = _sanitize_component(workspace_id)
    root = Path(settings.artifact_root).resolve()
    if not root.exists():
        return []
    pattern = f"{ws}__*__*.json"
    latest_by_artifact_id: dict[str, dict[str, Any]] = {}
    for path in root.glob(pattern):
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if artifact.get("schema_version") != "learning-v1":
            continue
        if artifact.get("source_type") != "learning_state":
            continue
        artifact_id = str(artifact.get("artifact_id", ""))
        if not artifact_id:
            continue
        current = latest_by_artifact_id.get(artifact_id)
        if current is None or int(artifact.get("artifact_version", 0)) >= int(current.get("artifact_version", 0)):
            latest_by_artifact_id[artifact_id] = artifact
    return sorted(
        latest_by_artifact_id.values(),
        key=lambda item: (
            str(item.get("manifest", {}).get("signed_at", "")),
            int(item.get("artifact_version", 0)),
        ),
        reverse=True,
    )


def _verify_learning_artifact(artifact: dict[str, Any], workspace_id: str, artifact_id: str) -> tuple[bool, str]:
    ok, reason_code, trust_status = verify_artifact(
        artifact,
        workspace_id,
        str(artifact.get("source_fingerprint", artifact.get("repo_fingerprint", ""))),
        artifact_id,
    )
    return ok, reason_code or trust_status


def _matching_learning_artifacts(
    *,
    workspace_id: str,
    source_id: str | None = None,
    state_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    artifacts = _load_learning_state_candidates(workspace_id)
    items: list[dict[str, Any]] = []
    for artifact in artifacts:
        artifact_id = str(artifact.get("artifact_id", ""))
        if source_id and artifact.get("source_id") != source_id:
            continue
        artifact_payload = artifact.get("payload", {})
        if state_type and artifact_payload.get("state_type") != state_type:
            continue
        ok, _ = _verify_learning_artifact(artifact, workspace_id, artifact_id)
        if not ok:
            continue
        items.append(artifact)
        if len(items) >= limit:
            break
    return items


def _learning_state_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_payload = artifact.get("payload", {})
    return {
        "artifact_id": str(artifact.get("artifact_id", "")),
        "artifact_version": artifact.get("artifact_version", 1),
        "schema_version": artifact.get("schema_version"),
        "source_id": artifact.get("source_id"),
        "source_revision": artifact.get("source_revision"),
        "source_fingerprint": artifact.get("source_fingerprint"),
        "state_type": artifact_payload.get("state_type"),
        "metadata": artifact_payload.get("metadata", {}),
        "signed_at": artifact.get("manifest", {}).get("signed_at"),
    }


@router.post("/v1/learning-state")
def publish_learning_state(req: LearningStatePublishRequest, authorization: str | None = Header(default=None)):
    disabled = _disabled_response()
    if disabled is not None:
        return disabled
    require_auth(authorization)
    if settings.trust_mode == "strict" and not settings.signing_key:
        raise HTTPException(
            status_code=500,
            detail={"reason_code": "internal_error", "message": "missing signing key"},
        )

    source_type = "learning_state"
    source_revision = _learning_revision(req.metadata)
    source_fingerprint = compute_source_fingerprint(
        req.workspace_id,
        source_type,
        req.source_id,
        source_revision,
    )
    artifact_id = _learning_artifact_id(req.workspace_id, req.source_id, req.state_type)
    try:
        baseline = load_latest_artifact(req.workspace_id, artifact_id)
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc
    artifact_version = int(baseline.get("artifact_version", 1) + 1) if baseline else 1
    payload = _learning_payload(req)

    unsigned = {
        "schema_version": "learning-v1",
        "workspace_id": req.workspace_id,
        "source_type": source_type,
        "source_id": req.source_id,
        "source_revision": source_revision,
        "source_fingerprint": source_fingerprint,
        "repo_fingerprint": source_fingerprint,
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "rebuild_reason": "learning_state_publish",
        "payload": payload,
    }
    artifact_hash = sha256_hex(canonical_json(unsigned))
    signature = sign_hash(artifact_hash, settings.signing_key) if settings.signing_key else ""
    envelope = ArtifactEnvelope(
        schema_version="learning-v1",
        workspace_id=req.workspace_id,
        source_type=source_type,
        source_id=req.source_id,
        source_revision=source_revision,
        source_fingerprint=source_fingerprint,
        repo_fingerprint=source_fingerprint,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        rebuild_reason="learning_state_publish",
        artifact_hash=artifact_hash,
        manifest=Manifest(
            signer=settings.signer,
            signed_at=_now_utc(),
            signature=signature,
            key_id=None,
        ),
        payload=payload,
    )
    envelope_dict = envelope.model_dump()
    try:
        stored_path = persist_artifact(envelope_dict)
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc
    return {
        "ok": True,
        "reason_code": "learning_state_published",
        "artifact_path": stored_path,
        **envelope_dict,
    }


@router.get("/v1/learning-state/{artifact_id}")
def read_learning_state(
    artifact_id: str,
    workspace_id: str = Query(min_length=1),
    authorization: str | None = Header(default=None),
):
    disabled = _disabled_response()
    if disabled is not None:
        return disabled
    require_auth(authorization)
    try:
        artifact = load_latest_artifact(workspace_id, artifact_id)
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc
    if artifact is None or artifact.get("schema_version") != "learning-v1":
        raise HTTPException(
            status_code=404,
            detail={"reason_code": "artifact_missing", "message": "artifact not found"},
        )
    ok, reason_code = _verify_learning_artifact(artifact, workspace_id, artifact_id)
    if not ok:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": reason_code, "message": reason_code},
        )
    return {"ok": True, "reason_code": "learning_state_success", **artifact}


@router.get("/v1/learning-states")
def list_learning_states(
    workspace_id: str = Query(min_length=1),
    source_id: str | None = None,
    state_type: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    authorization: str | None = Header(default=None),
):
    disabled = _disabled_response()
    if disabled is not None:
        return disabled
    require_auth(authorization)
    try:
        artifacts = _matching_learning_artifacts(
            workspace_id=workspace_id,
            source_id=source_id,
            state_type=state_type,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc

    items = [_learning_state_summary(artifact) for artifact in artifacts]

    return {
        "ok": True,
        "reason_code": "learning_state_success",
        "items": items,
        "count": len(items),
    }


@router.get("/v1/governance-report")
def read_governance_report(
    workspace_id: str = Query(min_length=1),
    source_id: str = GOVERNANCE_REPORT_SOURCE_ID,
    authorization: str | None = Header(default=None),
):
    disabled = _disabled_response()
    if disabled is not None:
        return disabled
    require_auth(authorization)
    try:
        artifacts = _matching_learning_artifacts(
            workspace_id=workspace_id,
            source_id=source_id,
            state_type=GOVERNANCE_REPORT_STATE_TYPE,
            limit=1,
        )
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc

    if not artifacts:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": "artifact_missing", "message": "governance report not found"},
        )

    return {"ok": True, "reason_code": "learning_state_success", **artifacts[0]}


@router.get("/v1/governance-reports")
def list_governance_reports(
    workspace_id: str = Query(min_length=1),
    source_id: str = GOVERNANCE_REPORT_SOURCE_ID,
    limit: int = Query(default=20, ge=1, le=500),
    authorization: str | None = Header(default=None),
):
    disabled = _disabled_response()
    if disabled is not None:
        return disabled
    require_auth(authorization)
    try:
        artifacts = _matching_learning_artifacts(
            workspace_id=workspace_id,
            source_id=source_id,
            state_type=GOVERNANCE_REPORT_STATE_TYPE,
            limit=limit,
        )
    except ValueError as exc:
        raise _http_error_for_artifact_error(str(exc)) from exc

    items = [_learning_state_summary(artifact) for artifact in artifacts]
    return {
        "ok": True,
        "reason_code": "learning_state_success",
        "items": items,
        "count": len(items),
    }
