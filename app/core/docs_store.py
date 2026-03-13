from __future__ import annotations

from typing import Any


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
        "index_meta": {
            "strategy": "docs_markdown_v1",
            "discovery_mode": discovery_mode,
        },
    }
