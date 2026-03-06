from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
import httpx

from app.models.schemas import IndexRequest, ArtifactEnvelope, Manifest
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.core.artifacts import persist_artifact, load_artifact
from app.core.indexer import build_payload_from_repo
from app.core.identity import REVISION_UNAVAILABLE, source_strategy
from app.config import settings
from app.security import require_auth
from app.metrics import metrics

router = APIRouter(dependencies=[Depends(require_auth)])


def _diff_counts(old_payload: dict, new_payload: dict) -> tuple[int, int]:
    old_files = {f.get("path", "") for f in old_payload.get("files", [])}
    new_files = {f.get("path", "") for f in new_payload.get("files", [])}
    changed = len(new_files.symmetric_difference(old_files))
    reused = len(new_files.intersection(old_files))
    return changed, reused


@router.post("/v1/index")
def create_index(req: IndexRequest):
    metrics.record_request()
    if settings.trust_mode == "strict" and not settings.signing_key:
        metrics.record_deny("internal_error")
        raise HTTPException(status_code=500, detail={"reason_code": "internal_error", "message": "missing signing key"})

    artifact_id = sha256_hex(f"{req.workspace_id}:{req.source_fingerprint}")[:24]
    current = load_artifact(req.workspace_id, req.source_fingerprint, artifact_id)
    if current and current.get("source_revision") == req.source_revision:
        current["rebuild_reason"] = "cache_hit_same_revision"
        current["artifact_version"] = int(current.get("artifact_version", 1))
        metrics.record_rebuild(
            rebuild_reason="cache_hit_same_revision",
            files_changed=0,
            files_reused=int(current.get("payload", {}).get("stats", {}).get("file_count", 0)),
        )
        metrics.record_success(current.get("payload", {}).get("token_savings_estimate", {}).get("saved_tokens_est"))
        return {"ok": True, "reason_code": "code_index_success", "artifact_path": "", **current}

    try:
        payload = build_payload_from_repo(req.repo_ref)
    except ValueError as exc:
        metrics.record_deny(str(exc))
        raise HTTPException(status_code=422, detail={"reason_code": str(exc), "message": str(exc)}) from exc
    except httpx.HTTPError as exc:
        metrics.record_deny("github_fetch_failed")
        raise HTTPException(status_code=502, detail={"reason_code": "github_fetch_failed", "message": str(exc)}) from exc

    strategy = source_strategy(req.source_type or "snapshot")
    if not current:
        rebuild_reason = "full_rebuild_first_index"
    elif req.source_revision == REVISION_UNAVAILABLE:
        rebuild_reason = "full_rebuild_revision_unavailable"
    elif strategy == "nondiffable":
        rebuild_reason = "full_rebuild_nondiffable_source"
    else:
        rebuild_reason = "incremental_changed_files"
    artifact_version = int(current.get("artifact_version", 1) + 1) if current else 1
    files_changed, files_reused = _diff_counts(current.get("payload", {}) if current else {}, payload)

    unsigned = {
        "schema_version": "c35-v1",
        "workspace_id": req.workspace_id,
        "source_type": req.source_type,
        "source_id": req.source_id,
        "source_revision": req.source_revision,
        "source_fingerprint": req.source_fingerprint,
        "repo_fingerprint": req.source_fingerprint,
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "rebuild_reason": rebuild_reason,
        "payload": payload,
    }
    artifact_hash = sha256_hex(canonical_json(unsigned))
    signature = sign_hash(artifact_hash, settings.signing_key) if settings.signing_key else ""

    envelope = ArtifactEnvelope(
        workspace_id=req.workspace_id,
        source_type=req.source_type or "snapshot",
        source_id=req.source_id or "",
        source_revision=req.source_revision or REVISION_UNAVAILABLE,
        source_fingerprint=req.source_fingerprint or "",
        repo_fingerprint=req.source_fingerprint or "",
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        rebuild_reason=rebuild_reason,
        artifact_hash=artifact_hash,
        manifest=Manifest(
            signer=settings.signer,
            signed_at=datetime.now(timezone.utc).isoformat(),
            signature=signature,
            key_id=None,
        ),
        payload=payload,
    )

    envelope_dict = envelope.model_dump()
    try:
        stored_path = persist_artifact(envelope_dict)
    except ValueError as exc:
        code = str(exc)
        metrics.record_deny(code)
        status = 403 if code == "artifact_path_outside_root" else 422
        raise HTTPException(status_code=status, detail={"reason_code": code, "message": code}) from exc

    metrics.record_rebuild(rebuild_reason=rebuild_reason, files_changed=files_changed, files_reused=files_reused)
    metrics.record_success(envelope_dict.get("payload", {}).get("token_savings_estimate", {}).get("saved_tokens_est"))
    return {"ok": True, "reason_code": "code_index_success", "artifact_path": stored_path, **envelope_dict}
