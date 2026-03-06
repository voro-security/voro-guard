from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import IndexRequest, ArtifactEnvelope, Manifest
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.core.artifacts import persist_artifact
from app.core.indexer import build_payload_from_repo
from app.config import settings
from app.security import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.post("/v1/index")
def create_index(req: IndexRequest):
    if settings.trust_mode == "strict" and not settings.signing_key:
        raise HTTPException(status_code=500, detail={"reason_code": "internal_error", "message": "missing signing key"})

    artifact_id = sha256_hex(f"{req.workspace_id}:{req.repo_fingerprint}")[:24]
    payload = build_payload_from_repo(req.repo_ref)

    unsigned = {
        "schema_version": "c35-v1",
        "workspace_id": req.workspace_id,
        "repo_fingerprint": req.repo_fingerprint,
        "artifact_id": artifact_id,
        "payload": payload,
    }
    artifact_hash = sha256_hex(canonical_json(unsigned))
    signature = sign_hash(artifact_hash, settings.signing_key) if settings.signing_key else ""

    envelope = ArtifactEnvelope(
        workspace_id=req.workspace_id,
        repo_fingerprint=req.repo_fingerprint,
        artifact_id=artifact_id,
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
        status = 403 if code == "artifact_path_outside_root" else 422
        raise HTTPException(status_code=status, detail={"reason_code": code, "message": code}) from exc

    return {"ok": True, "reason_code": "code_index_success", "artifact_path": stored_path, **envelope_dict}
