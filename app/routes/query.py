from fastapi import APIRouter, Depends, HTTPException

from app.metrics import metrics
from app.models.schemas import CallgraphRequest, GetRequest, OutlineRequest, QueryRequest, SearchRequest
from app.core.artifacts import load_artifact, verify_artifact
from app.core.callgraph import build_callgraph_from_file
from app.core.docs_store import get_docs_entry, get_docs_outline, search_docs
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
    "docs_search_not_supported": 422,
    "doc_target_required": 400,
}


def _execute_query(req: QueryRequest):
    metrics.record_request()
    if req.mode == "search" and not (req.query and req.query.strip()):
        metrics.record_deny("query_required")
        raise HTTPException(status_code=400, detail={"reason_code": "query_required", "message": "query is required"})
    try:
        artifact = load_artifact(req.workspace_id, req.source_fingerprint or req.repo_fingerprint or "", req.artifact_id)
    except ValueError as exc:
        code = str(exc)
        metrics.record_deny(code)
        status = _REASON_STATUS.get(code, 422)
        raise HTTPException(status_code=status, detail={"reason_code": code, "message": code}) from exc

    if artifact is None:
        metrics.record_deny("artifact_missing")
        raise HTTPException(status_code=404, detail={"reason_code": "artifact_missing", "message": "artifact not found"})

    ok, reason_code, trust_status = verify_artifact(
        artifact,
        req.workspace_id,
        req.source_fingerprint or req.repo_fingerprint or "",
        req.artifact_id,
    )
    if not ok:
        metrics.record_deny(reason_code)
        status = _REASON_STATUS.get(reason_code, 403)
        raise HTTPException(status_code=status, detail={"reason_code": reason_code, "message": trust_status})

    payload = artifact.get("payload", {})
    is_docs_artifact = artifact.get("schema_version") == "docs-v1"
    if is_docs_artifact:
        if req.mode == "search":
            results = search_docs(
                payload,
                req.query or "",
                allowed_visibility=req.allowed_visibility,
            )
        elif req.mode == "get":
            if not (req.doc_id or req.section_id):
                metrics.record_deny("doc_target_required")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "reason_code": "doc_target_required",
                        "message": "doc_id or section_id is required for docs artifacts",
                    },
                )
            entry = get_docs_entry(
                payload,
                doc_id=req.doc_id,
                section_id=req.section_id,
                allowed_visibility=req.allowed_visibility,
            )
            results = [entry] if entry else []
        else:
            results = get_docs_outline(payload, allowed_visibility=req.allowed_visibility)
    else:
        if req.mode == "search":
            results = run_search(payload, req.query or "")
        elif req.mode == "get":
            symbol = find_symbol(payload, req.symbol_id or "")
            results = [symbol] if symbol else []
        else:
            results = build_outline(payload)

    response = {
        "ok": True,
        "reason_code": "code_index_success",
        "artifact_trust": trust_status,
        "workspace_id": req.workspace_id,
        "source_type": artifact.get("source_type"),
        "source_id": artifact.get("source_id"),
        "source_revision": artifact.get("source_revision"),
        "source_fingerprint": artifact.get("source_fingerprint", req.source_fingerprint),
        "repo_fingerprint": artifact.get("repo_fingerprint", req.repo_fingerprint),
        "artifact_id": req.artifact_id,
        "artifact_version": artifact.get("artifact_version", 1),
        "rebuild_reason": artifact.get("rebuild_reason", "full_rebuild_first_index"),
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
    metrics.record_success(response["token_savings_estimate"].get("saved_tokens_est"))
    return response


@router.post("/v1/query")
def query_index(req: QueryRequest):
    return _execute_query(req)


@router.post("/v1/search")
def search_index(req: SearchRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            source_fingerprint=req.source_fingerprint,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="search",
            query=req.query,
            allowed_visibility=req.allowed_visibility,
        )
    )


@router.post("/v1/get")
def get_symbol(req: GetRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            source_fingerprint=req.source_fingerprint,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="get",
            symbol_id=req.symbol_id,
            doc_id=req.doc_id,
            section_id=req.section_id,
            allowed_visibility=req.allowed_visibility,
        )
    )


@router.post("/v1/outline")
def get_outline(req: OutlineRequest):
    return _execute_query(
        QueryRequest(
            workspace_id=req.workspace_id,
            source_fingerprint=req.source_fingerprint,
            repo_fingerprint=req.repo_fingerprint,
            artifact_id=req.artifact_id,
            mode="outline",
            allowed_visibility=req.allowed_visibility,
        )
    )


@router.get("/v1/metrics")
def get_metrics():
    return {"ok": True, "metrics": metrics.snapshot()}


@router.post("/v1/callgraph")
def get_callgraph(req: CallgraphRequest):
    metrics.record_request()
    entry_points, error = build_callgraph_from_file(
        req.file,
        entry_function=req.entry_function,
        max_depth=req.max_depth,
    )
    if error:
        # Graceful failure mode per spec: never raise 500 for missing entry/function.
        return {"entry_points": [], "error": error}
    return {"entry_points": entry_points}
