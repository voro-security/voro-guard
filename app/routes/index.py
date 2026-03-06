from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.models.schemas import IndexRequest, ArtifactEnvelope, Manifest
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.config import settings

router = APIRouter()


@router.post("/v1/index")
def create_index(req: IndexRequest):
    if settings.trust_mode == "strict" and not settings.signing_key:
        raise HTTPException(status_code=500, detail={"reason_code": "internal_error", "message": "missing signing key"})

    artifact_id = sha256_hex(f"{req.workspace_id}:{req.repo_fingerprint}")[:24]
    payload = {
        "repo_ref": req.repo_ref or "",
        "token_savings_estimate": {
            "baseline_tokens_est": 0,
            "indexed_tokens_est": 0,
            "saved_tokens_est": 0,
            "saved_percent_est": 0.0,
            "method": "heuristic",
            "confidence": "low",
        },
    }

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

    return {"ok": True, "reason_code": "code_index_success", **envelope.model_dump()}
