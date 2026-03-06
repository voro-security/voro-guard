from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import GetRequest, OutlineRequest, QueryRequest, SearchRequest
from app.core.artifacts import load_artifact, verify_artifact
from app.core.store import get_outline as build_outline
from app.core.store import get_symbol as find_symbol
from app.core.store import search_symbols as run_search
from app.security import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

_REASON_STATUS = {
    "artifact_missing": 404,
    "artifact_invalid": 422,
    "artifact_path_outside_root": 403,
    "artifact_untrusted_missing_manifest": 403,
    "artifact_untrusted_hash_mismatch": 403,
    "artifact_untrusted_signature_invalid": 403,
    "artifact_identity_mismatch": 403,
}


def _execute_query(req: QueryRequest):
    if req.mode == "search" and not (req.query and req.query.strip()):
        raise HTTPException(status_code=400, detail={"reason_code": "query_required", "message": "query is required"})
    if req.mode == "get" and not (req.symbol_id and req.symbol_id.strip()):
        raise HTTPException(status_code=400, detail={"reason_code": "symbol_id_required", "message": "symbol_id is required"})

    try:
        artifact = load_artifact(req.workspace_id, req.repo_fingerprint, req.artifact_id)
    except ValueError as exc:
        code = str(exc)
        status = _REASON_STATUS.get(code, 422)
        raise HTTPException(status_code=status, detail={"reason_code": code, "message": code}) from exc

    if artifact is None:
        raise HTTPException(status_code=404, detail={"reason_code": "artifact_missing", "message": "artifact not found"})

    ok, reason_code, trust_status = verify_artifact(artifact, req.workspace_id, req.repo_fingerprint, req.artifact_id)
    if not ok:
        status = _REASON_STATUS.get(reason_code, 403)
        raise HTTPException(status_code=status, detail={"reason_code": reason_code, "message": trust_status})

    payload = artifact.get("payload", {})
    if req.mode == "search":
        results = run_search(payload, req.query or "")
    elif req.mode == "get":
        symbol = find_symbol(payload, req.symbol_id or "")
        results = [symbol] if symbol else []
    else:
        results = build_outline(payload)

    return {
        "ok": True,
        "reason_code": "code_index_success",
        "artifact_trust": trust_status,
        "workspace_id": req.workspace_id,
        "repo_fingerprint": req.repo_fingerprint,
        "artifact_id": req.artifact_id,
        "mode": req.mode,
        "results": results,
        "token_savings_estimate": artifact.get("payload", {}).get(
            "token_savings_estimate",
            {
                "baseline_tokens_est": 0,
                "indexed_tokens_est": 0,
                "saved_tokens_est": 0,
                "saved_percent_est": 0.0,
                "method": "heuristic",
                "confidence": "low",
            },
        ),
    }


@router.post("/v1/query")
def query_index(req: QueryRequest):
    return _execute_query(req)


@router.post("/v1/search")
def search_index(req: SearchRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="search",
            query=req.query,
        )
    )


@router.post("/v1/get")
def get_symbol(req: GetRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="get",
            symbol_id=req.symbol_id,
        )
    )


@router.post("/v1/outline")
def get_outline(req: OutlineRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="outline",
        )
    )
