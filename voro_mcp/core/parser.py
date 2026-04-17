from __future__ import annotations

from pathlib import Path
import hashlib
import re

from voro_mcp.core.callgraph import parse_solidity_functions

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
    if lang == "solidity":
        return _extract_solidity_symbols(file_path, content)
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
            start = max(1, i - 2)
            end = min(len(lines), i + 2)
            snippet = "\n".join(lines[start - 1 : end])
            symbols.append(
                {
                    "id": symbol_id,
                    "kind": kind,
                    "name": name,
                    "file": file_path,
                    "line": i,
                    "signature": line.strip()[:200],
                    "language": lang,
                    "snippet_start_line": start,
                    "snippet_end_line": end,
                    "snippet": snippet[:2000],
                }
            )
            break
    return symbols


def _extract_solidity_symbols(file_path: str, content: str) -> list[dict]:
    lines = content.splitlines()
    symbols: list[dict] = []
    patterns = _PATTERNS.get("solidity", [])

    # Keep contract/interface extraction behavior unchanged.
    for i, line in enumerate(lines, start=1):
        for kind, pattern in patterns:
            if kind == "function":
                continue
            m = re.search(pattern, line)
            if not m:
                continue
            name = m.group(1)
            symbol_id = hashlib.sha256(f"{file_path}:{kind}:{name}:{i}".encode("utf-8")).hexdigest()[:16]
            start = max(1, i - 2)
            end = min(len(lines), i + 2)
            snippet = "\n".join(lines[start - 1 : end])
            symbols.append(
                {
                    "id": symbol_id,
                    "kind": kind,
                    "name": name,
                    "file": file_path,
                    "line": i,
                    "signature": line.strip()[:200],
                    "language": "solidity",
                    "snippet_start_line": start,
                    "snippet_end_line": end,
                    "snippet": snippet[:2000],
                }
            )
            break

    # Solidity function metadata with visibility/reachability.
    for fn in parse_solidity_functions(content).values():
        line = max(1, fn.line)
        src_line = lines[line - 1] if line - 1 < len(lines) else ""
        symbol_id = hashlib.sha256(
            f"{file_path}:function:{fn.name}:{line}".encode("utf-8")
        ).hexdigest()[:16]
        start = max(1, line - 2)
        end = min(len(lines), line + 2)
        snippet = "\n".join(lines[start - 1 : end])
        symbols.append(
            {
                "id": symbol_id,
                "kind": "function",
                "name": fn.name,
                "file": file_path,
                "line": line,
                "signature": src_line.strip()[:200],
                "language": "solidity",
                "visibility": fn.visibility,
                "payable": fn.payable,
                "reachable": fn.reachable,
                "snippet_start_line": start,
                "snippet_end_line": end,
                "snippet": snippet[:2000],
            }
        )

    symbols.sort(key=lambda s: (int(s.get("line", 0)), str(s.get("kind", "")), str(s.get("name", ""))))
    return symbols
