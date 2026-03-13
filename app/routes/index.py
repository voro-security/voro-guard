from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
import httpx

from app.models.schemas import IndexRequest, ArtifactEnvelope, Manifest
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.core.artifacts import persist_artifact, load_artifact, load_latest_artifact
from app.core.indexer import build_payload_from_repo
from app.core.docs_store import build_docs_payload_from_repo
from app.core.identity import REVISION_UNAVAILABLE, source_strategy, compute_artifact_identity
from app.config import settings
from app.security import require_auth
from app.metrics import metrics

router = APIRouter(dependencies=[Depends(require_auth)])


def _diff_counts(old_payload: dict, new_payload: dict) -> tuple[int, int]:
    new_meta = (new_payload or {}).get("index_meta", {})
    inc = new_meta.get("incremental", {}) if isinstance(new_meta, dict) else {}
    if isinstance(inc, dict) and isinstance(inc.get("changed_count"), int) and isinstance(inc.get("reused_count"), int):
        return int(inc.get("changed_count", 0)), int(inc.get("reused_count", 0))
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

    artifact_id = compute_artifact_identity(
        req.workspace_id,
        req.source_type or "snapshot",
        req.source_id or "",
        artifact_kind=req.index_kind,
    )
    exact = load_artifact(req.workspace_id, req.source_fingerprint, artifact_id)
    if exact and exact.get("source_revision") == req.source_revision:
        exact["rebuild_reason"] = "cache_hit_same_revision"
        exact["artifact_version"] = int(exact.get("artifact_version", 1))
        metrics.record_rebuild(
            rebuild_reason="cache_hit_same_revision",
            files_changed=0,
            files_reused=int(exact.get("payload", {}).get("stats", {}).get("file_count", 0)),
        )
        metrics.record_success(exact.get("payload", {}).get("token_savings_estimate", {}).get("saved_tokens_est"))
        return {"ok": True, "reason_code": "code_index_success", "artifact_path": "", **exact}

    baseline = exact or load_latest_artifact(req.workspace_id, artifact_id)
    strategy = source_strategy(req.source_type or "snapshot")
    incremental_allowed = strategy in {"diffable"} and (req.source_type or "").strip().lower() in {"github", "git"}

    try:
        if req.index_kind == "docs":
            payload = build_docs_payload_from_repo(req.repo_ref)
        else:
            payload = build_payload_from_repo(
                req.repo_ref,
                previous_payload=baseline.get("payload", {}) if baseline else None,
                incremental=incremental_allowed and baseline is not None and req.source_revision != REVISION_UNAVAILABLE,
            )
    except ValueError as exc:
        metrics.record_deny(str(exc))
        raise HTTPException(status_code=422, detail={"reason_code": str(exc), "message": str(exc)}) from exc
    except httpx.HTTPError as exc:
        metrics.record_deny("github_fetch_failed")
        raise HTTPException(status_code=502, detail={"reason_code": "github_fetch_failed", "message": str(exc)}) from exc

    if not baseline:
        rebuild_reason = "full_rebuild_first_index"
    elif req.source_revision == REVISION_UNAVAILABLE:
        rebuild_reason = "full_rebuild_revision_unavailable"
    elif not incremental_allowed:
        rebuild_reason = "full_rebuild_nondiffable_source"
    else:
        rebuild_reason = "incremental_changed_files"
    artifact_version = int(baseline.get("artifact_version", 1) + 1) if baseline else 1
    files_changed, files_reused = _diff_counts(baseline.get("payload", {}) if baseline else {}, payload)

    schema_version = "docs-v1" if req.index_kind == "docs" else "c35-v1"

    unsigned = {
        "schema_version": schema_version,
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
        schema_version=schema_version,
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
