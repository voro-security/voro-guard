from __future__ import annotations

from pathlib import Path
import hashlib
import re

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".php": "php",
    ".sol": "solidity",
}

_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "python": [
        ("class", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "javascript": [
        ("class", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        ("function", r"^\s*const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\("),
    ],
    "typescript": [
        ("class", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("interface", r"^\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("type", r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s*="),
        ("function", r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "go": [
        ("type", r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:struct|interface)"),
        ("function", r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "rust": [
        ("struct", r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("enum", r"^\s*(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "java": [
        ("class", r"^\s*(?:public\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("interface", r"^\s*(?:public\s+)?interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("method", r"^\s*(?:public|protected|private)\s+[\w<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "php": [
        ("class", r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
    "solidity": [
        ("contract", r"^\s*contract\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("interface", r"^\s*interface\s+([A-Za-z_][A-Za-z0-9_]*)"),
        ("function", r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
    ],
}


def language_for_path(path: str) -> str | None:
    return LANGUAGE_EXTENSIONS.get(Path(path).suffix.lower())


def extract_symbols(file_path: str, content: str) -> list[dict]:
    lang = language_for_path(file_path)
    if not lang:
        return []
    patterns = _PATTERNS.get(lang, [])
    lines = content.splitlines()
    symbols: list[dict] = []
    for i, line in enumerate(lines, start=1):
        for kind, pattern in patterns:
            m = re.search(pattern, line)
            if not m:
                continue
            name = m.group(1)
            symbol_id = hashlib.sha256(f"{file_path}:{kind}:{name}:{i}".encode("utf-8")).hexdigest()[:16]
            symbols.append(
                {
                    "id": symbol_id,
                    "kind": kind,
                    "name": name,
                    "file": file_path,
                    "line": i,
                    "signature": line.strip()[:200],
                    "language": lang,
                }
            )
            break
    return symbols

