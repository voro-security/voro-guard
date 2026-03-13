from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.docs_ingest import discover_local_docs
from app.core.docs_parser import parse_markdown_document


def build_docs_payload(
    repo_ref: str,
    parsed_documents: list[dict[str, Any]],
    discovery_mode: str = "default",
) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    for item in parsed_documents:
        document = item.get("document")
        if isinstance(document, dict):
            documents.append(document)
        doc_sections = item.get("sections")
        if isinstance(doc_sections, list):
            sections.extend(s for s in doc_sections if isinstance(s, dict))

    return {
        "repo_ref": repo_ref,
        "documents": documents,
        "sections": sections,
        "stats": {
            "document_count": len(documents),
            "section_count": len(sections),
        },
        "token_savings_estimate": {
            "baseline_tokens_est": 0,
            "indexed_tokens_est": 0,
            "saved_tokens_est": 0,
            "saved_percent_est": 0.0,
            "method": "heuristic",
            "confidence": "low",
        },
        "index_meta": {
            "strategy": "docs_markdown_v1",
            "discovery_mode": discovery_mode,
        },
    }


def build_docs_payload_from_repo(
    repo_ref: str | None,
    default_visibility: str = "public",
) -> dict[str, Any]:
    if not repo_ref:
        return build_docs_payload("", [])

    root = Path(repo_ref).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("docs_source_unsupported")

    docs = discover_local_docs(root)
    parsed_documents = [
        parse_markdown_document(
            path.relative_to(root).as_posix(),
            path.read_text(encoding="utf-8"),
            default_visibility=default_visibility,
        )
        for path in docs
    ]
    return build_docs_payload(str(root), parsed_documents)
