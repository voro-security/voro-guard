from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_VISIBILITY_RE = re.compile(r"\b(public|external|internal|private)\b")
_PAYABLE_RE = re.compile(r"\bpayable\b")

_FUNC_RE = re.compile(
    r"(?P<prefix>\bfunction\s+)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?P<modifiers>[^{};]*)\{",
    re.MULTILINE,
)
_LEGACY_FALLBACK_RE = re.compile(
    r"(?P<prefix>\bfunction)\s*\([^)]*\)\s*(?P<modifiers>[^{};]*)\{",
    re.MULTILINE,
)
_FALLBACK_RECEIVE_RE = re.compile(
    r"\b(?P<name>fallback|receive)\s*\([^)]*\)\s*(?P<modifiers>[^{};]*)\{",
    re.MULTILINE,
)
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_SKIP_CALLEES = {
    "if",
    "for",
    "while",
    "require",
    "assert",
    "revert",
    "emit",
    "return",
    "new",
}


@dataclass
class FunctionCall:
    name: str
    line: int


@dataclass
class SolidityFunction:
    name: str
    visibility: str
    line: int
    payable: bool
    reachable: bool
    calls: list[FunctionCall]


def _line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_block_end(text: str, open_brace_index: int) -> int | None:
    depth = 0
    i = open_brace_index
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _visibility_for(modifiers: str, *, force_external: bool = False) -> str:
    if force_external:
        return "external"
    m = _VISIBILITY_RE.search(modifiers or "")
    return m.group(1) if m else "internal"


def _is_payable(modifiers: str) -> bool:
    return bool(_PAYABLE_RE.search(modifiers or ""))


def parse_solidity_functions(source: str) -> dict[str, SolidityFunction]:
    functions: dict[str, SolidityFunction] = {}
    matches: list[tuple[str, int, str, bool]] = []

    for m in _FUNC_RE.finditer(source):
        matches.append((m.group("name"), m.start(), m.group("modifiers") or "", False))
    for m in _FALLBACK_RECEIVE_RE.finditer(source):
        matches.append((m.group("name"), m.start(), m.group("modifiers") or "", True))
    for m in _LEGACY_FALLBACK_RE.finditer(source):
        # Legacy unnamed fallback; modern fallback()/receive() already covered above.
        if _FALLBACK_RECEIVE_RE.search(m.group(0)):
            continue
        matches.append(("fallback", m.start(), m.group("modifiers") or "", True))

    for name, start, modifiers, force_external in matches:
        open_idx = source.find("{", start)
        if open_idx < 0:
            continue
        end_idx = _find_block_end(source, open_idx)
        if end_idx is None:
            continue

        line = _line_for_offset(source, start)
        visibility = _visibility_for(modifiers, force_external=force_external)
        payable = _is_payable(modifiers)
        reachable = name in {"fallback", "receive"} or visibility in {"public", "external"}
        body = source[open_idx + 1 : end_idx]

        calls: list[FunctionCall] = []
        for c in _CALL_RE.finditer(body):
            callee = c.group(1)
            if callee in _SKIP_CALLEES:
                continue
            call_line = _line_for_offset(source, open_idx + 1 + c.start())
            calls.append(FunctionCall(name=callee, line=call_line))

        functions[name] = SolidityFunction(
            name=name,
            visibility=visibility,
            line=line,
            payable=payable,
            reachable=reachable,
            calls=calls,
        )

    return functions


def build_callgraph(source: str, entry_function: str, max_depth: int = 10) -> tuple[list[dict], str | None]:
    funcs = parse_solidity_functions(source)
    root = funcs.get(entry_function)
    if root is None:
        return [], f"entry_function '{entry_function}' not found"

    def walk(name: str, depth: int, stack: set[str]) -> dict:
        fn = funcs.get(name)
        if fn is None:
            return {
                "name": name,
                "visibility": "unknown",
                "line": 0,
                "payable": False,
                "reachable": False,
                "calls": [],
            }
        if depth >= max_depth:
            return {
                "name": fn.name,
                "visibility": fn.visibility,
                "line": fn.line,
                "payable": fn.payable,
                "reachable": fn.reachable,
                "calls": [],
            }

        calls: list[dict] = []
        for c in fn.calls:
            if c.name in stack:
                calls.append(
                    {
                        "name": c.name,
                        "visibility": "recursive",
                        "line": c.line,
                        "payable": False,
                        "reachable": False,
                        "calls": [],
                    }
                )
                continue
            if c.name in funcs:
                calls.append(walk(c.name, depth + 1, stack | {c.name}))
            else:
                calls.append(
                    {
                        "name": c.name,
                        "visibility": "unknown",
                        "line": c.line,
                        "payable": False,
                        "reachable": False,
                        "calls": [],
                    }
                )

        return {
            "name": fn.name,
            "visibility": fn.visibility,
            "line": fn.line,
            "payable": fn.payable,
            "reachable": fn.reachable,
            "calls": calls,
        }

    return [walk(root.name, 0, {root.name})], None


def build_callgraph_from_file(file_path: str, entry_function: str, max_depth: int = 10) -> tuple[list[dict], str | None]:
    p = Path(file_path)
    if not p.is_absolute():
        return [], "file must be an absolute path"
    if not p.exists():
        return [], "file not found"
    if p.suffix.lower() != ".sol":
        return [], "only .sol files are supported"
    source = p.read_text(encoding="utf-8", errors="replace")
    return build_callgraph(source, entry_function=entry_function, max_depth=max_depth)
