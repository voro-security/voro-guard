from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import os
import time

import httpx
 
from voro_mcp.config import settings
from voro_mcp.core.ingest import discover_local_files, read_text_file
from voro_mcp.core.parser import extract_symbols, language_for_path
from voro_mcp.core.store import build_index_payload


def _is_github_ref(repo_ref: str) -> bool:
    if repo_ref.startswith("https://github.com/"):
        return True
    if repo_ref.count("/") == 1 and "://" not in repo_ref and not repo_ref.startswith("/"):
        owner, repo = repo_ref.split("/", 1)
        return bool(owner) and bool(repo)
    return False


def _parse_github_owner_repo(repo_ref: str) -> tuple[str, str]:
    raw = repo_ref.strip().removesuffix(".git")
    if raw.startswith("https://github.com/"):
        parsed = urlparse(raw)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("invalid_github_repo_ref")
        return parts[0], parts[1]
    if raw.count("/") == 1 and "://" not in raw:
        owner, repo = raw.split("/", 1)
        if owner and repo:
            return owner, repo
    raise ValueError("invalid_github_repo_ref")


def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _fetch_github_tree(owner: str, repo: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD"
    resp = httpx.get(url, params={"recursive": "1"}, headers=_github_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("tree", [])


def _fetch_github_content(owner: str, repo: str, file_path: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    headers = _github_headers()
    headers["Accept"] = "application/vnd.github.v3.raw"
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def _tree_blob_map(tree: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in tree:
        if entry.get("type") != "blob":
            continue
        p = str(entry.get("path", ""))
        if not p:
            continue
        out[p] = str(entry.get("sha", ""))
    return out


def _group_symbols_by_file(symbols: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols:
        p = str(sym.get("file", ""))
        out.setdefault(p, []).append(sym)
    return out


def _build_payload_from_github(
    repo_ref: str,
    previous_payload: dict[str, Any] | None = None,
    incremental: bool = False,
) -> dict[str, Any]:
    owner, repo = _parse_github_owner_repo(repo_ref)
    tree = _fetch_github_tree(owner, repo)
    blob_map = _tree_blob_map(tree)

    file_entries: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    max_files = max(1, settings.max_files)
    max_size = max(1, settings.max_file_size_bytes)
    deadline = time.monotonic() + max(1, settings.index_timeout_seconds)

    previous_files = {
        str(f.get("path", "")): f
        for f in (previous_payload or {}).get("files", [])
        if isinstance(f, dict) and isinstance(f.get("path"), str)
    }
    previous_symbols = _group_symbols_by_file(
        [s for s in (previous_payload or {}).get("symbols", []) if isinstance(s, dict)]
    )
    previous_blob_map = (
        (((previous_payload or {}).get("index_meta") or {}).get("github_blob_map") or {})
        if isinstance((previous_payload or {}).get("index_meta"), dict)
        else {}
    )

    selected_entries: list[dict[str, Any]] = []
    for entry in tree:
        if time.monotonic() > deadline:
            break
        if len(selected_entries) >= max_files:
            break
        if entry.get("type") != "blob":
            continue
        path = entry.get("path", "")
        size = int(entry.get("size", 0) or 0)
        if size > max_size:
            continue
        if any(seg in path for seg in ("/node_modules/", "/dist/", "/build/", "/.git/")):
            continue
        if path.startswith(("node_modules/", "dist/", "build/", ".git/")):
            continue
        if language_for_path(path) is None:
            continue
        selected_entries.append(entry)

    changed_paths: set[str] = set()
    deleted_paths: set[str] = set()
    reused_paths: set[str] = set()
    if incremental and previous_payload:
        selected_paths = {str(e.get("path", "")) for e in selected_entries}
        previous_paths = set(previous_files.keys())
        deleted_paths = previous_paths - selected_paths
        for e in selected_entries:
            p = str(e.get("path", ""))
            if previous_blob_map.get(p) == blob_map.get(p):
                reused_paths.add(p)
            else:
                changed_paths.add(p)
    else:
        changed_paths = {str(e.get("path", "")) for e in selected_entries}

    for path in sorted(reused_paths):
        meta = previous_files.get(path)
        if not meta:
            continue
        file_entries.append(meta)
        symbols.extend(previous_symbols.get(path, []))

    for entry in selected_entries:
        path = str(entry.get("path", ""))
        if path not in changed_paths:
            continue
        if time.monotonic() > deadline:
            break
        try:
            content = _fetch_github_content(owner, repo, path)
        except httpx.HTTPError:
            continue
        approx_tokens = max(1, len(content) // 4)
        file_entries.append(
            {
                "path": path,
                "language": language_for_path(path),
                "line_count": len(content.splitlines()),
                "approx_tokens": approx_tokens,
                "blob_sha": blob_map.get(path, ""),
            }
        )
        symbols.extend(extract_symbols(path, content)[: max(1, settings.max_symbols_per_file)])

    return build_index_payload(
        f"{owner}/{repo}",
        file_entries,
        symbols,
        index_meta={
            "strategy": "diffable",
            "github_blob_map": blob_map,
            "incremental": {
                "enabled": bool(incremental and previous_payload),
                "changed_files": sorted(changed_paths),
                "reused_files": sorted(reused_paths),
                "deleted_files": sorted(deleted_paths),
                "changed_count": len(changed_paths) + len(deleted_paths),
                "reused_count": len(reused_paths),
            },
        },
    )


def build_payload_from_repo(
    repo_ref: str | None,
    previous_payload: dict[str, Any] | None = None,
    incremental: bool = False,
) -> dict[str, Any]:
    if not repo_ref:
        return build_index_payload("", [], [])

    if _is_github_ref(repo_ref):
        return _build_payload_from_github(
            repo_ref,
            previous_payload=previous_payload,
            incremental=incremental,
        )

    root = Path(repo_ref).expanduser().resolve()
    files = (
        discover_local_files(
            repo_root=root,
            max_files=max(1, settings.max_files),
            max_size=max(1, settings.max_file_size_bytes),
        )
        if root.exists() and root.is_dir()
        else []
    )
    deadline = time.monotonic() + max(1, settings.index_timeout_seconds)

    file_entries: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    for file_path in files:
        if time.monotonic() > deadline:
            break
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
        symbols.extend(extract_symbols(rel_path, content)[: max(1, settings.max_symbols_per_file)])

    repo_label = str(root)
    if not root.exists() or not root.is_dir():
        # Keep deterministic output for unknown refs.
        repo_label = os.path.expanduser(repo_ref)
    return build_index_payload(
        repo_label,
        file_entries,
        symbols,
        index_meta={
            "strategy": "local_repo",
            "incremental": {
                "enabled": False,
                "changed_files": [],
                "reused_files": [],
                "deleted_files": [],
                "changed_count": len(file_entries),
                "reused_count": 0,
            },
        },
    )
