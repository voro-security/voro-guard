import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.docs_ingest import discover_local_docs
from app.core.docs_parser import parse_markdown_document
from app.core.docs_store import build_docs_payload
from app.models.schemas import IndexRequest
from app.routes.index import create_index
from app.config import settings


def test_discover_local_docs_and_build_payload(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "ops").mkdir(parents=True, exist_ok=True)
    (repo / "dist").mkdir(parents=True, exist_ok=True)

    (repo / "README.md").write_text("# Title\n\nIntro paragraph.\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("# Notes\n\nAgent notes.\n", encoding="utf-8")
    (repo / "STATUS.md").write_text("# Status\n\nCurrent state.\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text(
        "---\nvisibility: pro\n---\n## Guide\n\nGuide text.\n",
        encoding="utf-8",
    )
    (repo / "ops" / "runbook.md").write_text("## Runbook\n\nRunbook text.\n", encoding="utf-8")
    (repo / "dist" / "ignored.md").write_text("## Ignore\n\nNope.\n", encoding="utf-8")
    (repo / "notes.txt").write_text("not markdown", encoding="utf-8")

    discovered = discover_local_docs(repo)
    rel_paths = [path.relative_to(repo).as_posix() for path in discovered]

    assert rel_paths == [
        "CLAUDE.md",
        "README.md",
        "STATUS.md",
        "docs/guide.md",
        "ops/runbook.md",
    ]

    parsed = [
        parse_markdown_document(path.relative_to(repo).as_posix(), path.read_text(encoding="utf-8"))
        for path in discovered
    ]
    payload = build_docs_payload(str(repo), parsed)

    assert payload["stats"]["document_count"] == 5
    assert payload["stats"]["section_count"] == 5
    assert payload["index_meta"]["strategy"] == "docs_markdown_v1"
    doc_by_path = {doc["path"]: doc for doc in payload["documents"]}
    assert doc_by_path["docs/guide.md"]["visibility"] == "pro"
    guide_sections = [section for section in payload["sections"] if section["doc_id"] == doc_by_path["docs/guide.md"]["doc_id"]]
    assert len(guide_sections) == 1
    assert guide_sections[0]["visibility"] == "pro"


def test_create_index_supports_docs_artifact_flow(tmp_path: Path) -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"
    settings.artifact_root = str(tmp_path / "artifacts")

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "README.md").write_text("---\nvisibility: internal\n---\n# Intro\n\nHello.\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("## Guide\n\nGuide body.\n", encoding="utf-8")

    indexed = create_index(
        IndexRequest(
            workspace_id="ws1",
            index_kind="docs",
            source_type="local_repo",
            source_id="repo",
            source_revision="r1",
            repo_ref=str(repo),
        )
    )

    assert indexed["schema_version"] == "docs-v1"
    assert indexed["payload"]["stats"]["document_count"] == 2
    assert indexed["payload"]["stats"]["section_count"] == 2
    assert indexed["payload"]["documents"][0]["path"] == "README.md"
    assert indexed["payload"]["documents"][0]["visibility"] == "internal"
