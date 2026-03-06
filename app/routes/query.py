from fastapi import APIRouter, HTTPException
from app.models.schemas import QueryRequest

router = APIRouter()


@router.post("/v1/query")
def query_index(req: QueryRequest):
    if req.mode == "search" and not (req.query and req.query.strip()):
        raise HTTPException(status_code=400, detail={"reason_code": "query_required", "message": "query is required"})
    if req.mode == "get" and not (req.symbol_id and req.symbol_id.strip()):
        raise HTTPException(status_code=400, detail={"reason_code": "symbol_id_required", "message": "symbol_id is required"})

    return {
        "ok": True,
        "reason_code": "code_index_success",
        "workspace_id": req.workspace_id,
        "repo_fingerprint": req.repo_fingerprint,
        "artifact_id": req.artifact_id,
        "mode": req.mode,
        "results": [],
        "token_savings_estimate": {
            "baseline_tokens_est": 0,
            "indexed_tokens_est": 0,
            "saved_tokens_est": 0,
            "saved_percent_est": 0.0,
            "method": "heuristic",
            "confidence": "low",
        },
    }
