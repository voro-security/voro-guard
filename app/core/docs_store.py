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


def _visibility_allowed(value: str, allowed: list[str] | None) -> bool:
    if not allowed:
        return True
    return value in set(allowed)


def get_docs_entry(
    payload: dict[str, Any],
    *,
    doc_id: str | None = None,
    section_id: str | None = None,
    allowed_visibility: list[str] | None = None,
) -> dict[str, Any] | None:
    documents = payload.get("documents", [])
    sections = payload.get("sections", [])

    docs_by_id = {
        str(doc.get("doc_id", "")): doc
        for doc in documents
        if isinstance(doc, dict) and isinstance(doc.get("doc_id"), str)
    }
    sections_by_doc: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        parent_id = str(section.get("doc_id", ""))
        sections_by_doc.setdefault(parent_id, []).append(section)

    if section_id:
        for section in sections:
            if not isinstance(section, dict) or section.get("section_id") != section_id:
                continue
            document = docs_by_id.get(str(section.get("doc_id", "")))
            if not isinstance(document, dict):
                return None
            visibility = str(document.get("visibility", section.get("visibility", "public")))
            if not _visibility_allowed(visibility, allowed_visibility):
                return None
            return {
                "document": document,
                "section": {
                    **section,
                    "visibility": visibility,
                },
            }
        return None

    if doc_id:
        document = docs_by_id.get(doc_id)
        if not isinstance(document, dict):
            return None
        visibility = str(document.get("visibility", "public"))
        if not _visibility_allowed(visibility, allowed_visibility):
            return None
        visible_sections = [
            {
                **section,
                "visibility": visibility,
            }
            for section in sorted(
                sections_by_doc.get(doc_id, []),
                key=lambda item: (
                    int(item.get("start_line", 0)),
                    str(item.get("section_id", "")),
                ),
            )
        ]
        return {
            "document": document,
            "sections": visible_sections,
        }

    return None


def get_docs_outline(
    payload: dict[str, Any],
    *,
    allowed_visibility: list[str] | None = None,
) -> dict[str, Any]:
    documents = payload.get("documents", [])
    sections = payload.get("sections", [])
    sections_by_doc: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        if not isinstance(section, dict):
            continue
        parent_id = str(section.get("doc_id", ""))
        sections_by_doc.setdefault(parent_id, []).append(section)

    outline_documents: list[dict[str, Any]] = []
    total_sections = 0
    for document in sorted(
        [doc for doc in documents if isinstance(doc, dict)],
        key=lambda item: str(item.get("path", "")),
    ):
        visibility = str(document.get("visibility", "public"))
        if not _visibility_allowed(visibility, allowed_visibility):
            continue
        doc_id = str(document.get("doc_id", ""))
        doc_sections = sorted(
            sections_by_doc.get(doc_id, []),
            key=lambda item: (
                int(item.get("start_line", 0)),
                str(item.get("section_id", "")),
            ),
        )
        outline_sections = [
            {
                "section_id": section.get("section_id"),
                "heading": section.get("heading"),
                "heading_level": section.get("heading_level"),
                "heading_path": section.get("heading_path"),
                "start_line": section.get("start_line"),
                "end_line": section.get("end_line"),
                "summary": section.get("summary"),
                "visibility": visibility,
            }
            for section in doc_sections
        ]
        total_sections += len(outline_sections)
        outline_documents.append(
            {
                "doc_id": document.get("doc_id"),
                "path": document.get("path"),
                "title": document.get("title"),
                "status": document.get("status"),
                "class": document.get("class"),
                "authority": document.get("authority"),
                "visibility": visibility,
                "section_count": len(outline_sections),
                "sections": outline_sections,
            }
        )

    return {
        "summary": {
            "document_count": len(outline_documents),
            "section_count": total_sections,
        },
        "documents": outline_documents,
    }
