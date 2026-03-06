from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import os
import time

import httpx
 
from app.config import settings
from app.core.ingest import discover_local_files, read_text_file
from app.core.parser import extract_symbols, language_for_path
from app.core.store import build_index_payload


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


def _build_payload_from_github(repo_ref: str) -> dict[str, Any]:
    owner, repo = _parse_github_owner_repo(repo_ref)
    tree = _fetch_github_tree(owner, repo)

    file_entries: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    max_files = max(1, settings.max_files)
    max_size = max(1, settings.max_file_size_bytes)
    deadline = time.monotonic() + max(1, settings.index_timeout_seconds)

    for entry in tree:
        if time.monotonic() > deadline:
            break
        if len(file_entries) >= max_files:
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
            }
        )
        symbols.extend(extract_symbols(path, content)[: max(1, settings.max_symbols_per_file)])

    return build_index_payload(f"{owner}/{repo}", file_entries, symbols)


def build_payload_from_repo(repo_ref: str | None) -> dict[str, Any]:
    if not repo_ref:
        return build_index_payload("", [], [])

    if _is_github_ref(repo_ref):
        return _build_payload_from_github(repo_ref)

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
    return build_index_payload(repo_label, file_entries, symbols)
