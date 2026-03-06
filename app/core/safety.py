from __future__ import annotations

from pathlib import Path
import os
import fnmatch

SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa",
    "id_ed25519",
    "*.p12",
    "*.pfx",
    "*secret*",
    "*token*",
    ".npmrc",
    ".pypirc",
    "credentials.json",
)

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".mp3",
    ".mp4",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".class",
    ".pyc",
    ".woff",
    ".woff2",
}


def path_within_root(root: Path, target: Path) -> bool:
    try:
        root_r = root.resolve()
        target_r = target.resolve()
        return os.path.commonpath([str(root_r), str(target_r)]) == str(root_r)
    except (OSError, ValueError):
        return False


def is_symlink_escape(root: Path, target: Path) -> bool:
    if not target.is_symlink():
        return False
    return not path_within_root(root, target)


def is_secret_file(path: str) -> bool:
    name = os.path.basename(path).lower()
    lower = path.lower()
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(lower, p) for p in SECRET_PATTERNS)


def is_binary_extension(path: str) -> bool:
    return Path(path).suffix.lower() in BINARY_EXTENSIONS

