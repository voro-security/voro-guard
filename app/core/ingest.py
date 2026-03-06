from __future__ import annotations

from pathlib import Path

from app.core.parser import LANGUAGE_EXTENSIONS
from app.core.safety import is_binary_extension, is_secret_file, is_symlink_escape, path_within_root

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "target",
    ".mypy_cache",
}


def discover_local_files(repo_root: Path, max_files: int = 500, max_size: int = 500 * 1024) -> list[Path]:
    root = repo_root.resolve()
    if not root.exists() or not root.is_dir():
        return []

    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if path.is_dir():
            if path.name in SKIP_DIRS:
                # Skip whole subtree by not descending further is not directly supported with rglob.
                continue
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path_within_root(root, path):
            continue
        if is_symlink_escape(root, path):
            continue
        rel = path.relative_to(root).as_posix()
        if Path(rel).suffix.lower() not in LANGUAGE_EXTENSIONS:
            continue
        if is_secret_file(rel) or is_binary_extension(rel):
            continue
        try:
            if path.stat().st_size > max_size:
                continue
            files.append(path)
        except OSError:
            continue
    return files


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")

