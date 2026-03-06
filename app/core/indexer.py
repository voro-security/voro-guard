from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.ingest import discover_local_files, read_text_file
from app.core.parser import extract_symbols, language_for_path
from app.core.store import build_index_payload


def build_payload_from_repo(repo_ref: str | None) -> dict[str, Any]:
    if not repo_ref:
        return build_index_payload("", [], [])

    root = Path(repo_ref).expanduser().resolve()
    files = discover_local_files(repo_root=root) if root.exists() and root.is_dir() else []

    file_entries: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    for file_path in files:
        rel_path = file_path.relative_to(root).as_posix()
        content = read_text_file(file_path)
        approx_tokens = max(1, len(content) // 4)
        file_entries.append(
            {
                "path": rel_path,
                "language": language_for_path(rel_path),
                "line_count": len(content.splitlines()),
                "approx_tokens": approx_tokens,
            }
        )
        symbols.extend(extract_symbols(rel_path, content))

    return build_index_payload(str(root), file_entries, symbols)
