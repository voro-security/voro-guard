import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.docs_parser import parse_markdown_document


def test_parse_markdown_document_extracts_frontmatter_headers_and_sections() -> None:
    content = (
        "---\n"
        "title: Docs Parser\n"
        "visibility: internal\n"
        "---\n"
        "# Status: ACTIVE\n"
        "# Class: binding\n"
        "# Authority: human-written\n"
        "# Generator: unknown\n"
        "# Editing Rule: human-written only\n"
        "\n"
        "## Purpose\n"
        "This parser extracts sections deterministically.\n"
        "\n"
        "## Purpose\n"
        "Repeated headings still need stable unique ids.\n"
    )

    parsed = parse_markdown_document("docs/parser.md", content)
    document = parsed["document"]
    sections = parsed["sections"]

    assert document["title"] == "Docs Parser"
    assert document["status"] == "ACTIVE"
    assert document["class"] == "binding"
    assert document["authority"] == "human-written"
    assert document["visibility"] == "internal"
    assert document["visibility_source"] == "frontmatter"
    assert document["section_count"] == 2

    assert len(sections) == 2
    assert sections[0]["heading"] == "Purpose"
    assert sections[0]["heading_path"] == ["Purpose"]
    assert sections[0]["visibility"] == "internal"
    assert sections[0]["summary"] == "This parser extracts sections deterministically."
    assert sections[0]["section_id"] != sections[1]["section_id"]
    assert sections[1]["heading"] == "Purpose"


def test_parse_markdown_document_creates_synthetic_section_without_headings() -> None:
    content = (
        "---\n"
        "title: Plain Doc\n"
        "---\n"
        "# Status: ACTIVE\n"
        "\n"
        "This document has no ATX headings.\n"
        "It should become one synthetic section.\n"
    )

    parsed = parse_markdown_document("README.md", content)
    document = parsed["document"]
    sections = parsed["sections"]

    assert document["visibility"] == "public"
    assert document["visibility_source"] == "default_visibility"
    assert len(sections) == 1
    assert sections[0]["heading"] == ""
    assert sections[0]["heading_level"] == 0
    assert sections[0]["heading_path"] == []
    assert sections[0]["summary"] == "This document has no ATX headings. It should become one synthetic section."
