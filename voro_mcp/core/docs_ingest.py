from __future__ import annotations

from pathlib import Path, PurePosixPath
import fnmatch

from voro_mcp.core.safety import is_binary_extension, is_secret_file, is_symlink_escape, path_within_root

DEFAULT_INCLUDE_GLOBS = [
    "README.md",
    "CLAUDE.md",
    "STATUS.md",
    "docs/**/*.md",
    "ops/**/*.md",
]

DEFAULT_EXCLUDE_GLOBS = [
    ".git/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "vendor/**",
    "*.min.*",
]


def _matches_any(path: str, patterns: list[str]) -> bool:
    pure_path = PurePosixPath(path)
    expanded_patterns: list[str] = []
    for pattern in patterns:
        expanded_patterns.append(pattern)
        if "/**/" in pattern:
            expanded_patterns.append(pattern.replace("/**/", "/"))
    return any(pure_path.match(pattern) or fnmatch.fnmatch(path, pattern) for pattern in expanded_patterns)


def discover_local_docs(
    repo_root: Path,
    max_files: int = 500,
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
) -> list[Path]:
    root = repo_root.resolve()
    if not root.exists() or not root.is_dir():
        return []

    include = include_globs or DEFAULT_INCLUDE_GLOBS
    exclude = exclude_globs or DEFAULT_EXCLUDE_GLOBS

    candidates = sorted(root.rglob("*.md"))
    files: list[Path] = []
    for path in candidates:
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if not path_within_root(root, path):
            continue
        if is_symlink_escape(root, path):
            continue

        rel = path.relative_to(root).as_posix()
        if not _matches_any(rel, include):
            continue
        if _matches_any(rel, exclude):
            continue
        if is_secret_file(rel) or is_binary_extension(rel):
            continue
        files.append(path)
    return files
