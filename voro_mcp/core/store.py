from __future__ import annotations

from typing import Any


def build_index_payload(
    repo_ref: str,
    files: list[dict[str, Any]],
    symbols: list[dict[str, Any]],
    index_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_tokens = sum(int(f.get("approx_tokens", 0)) for f in files)
    indexed_tokens = min(baseline_tokens, max(0, len(symbols) * 60 + len(files) * 20))
    saved_tokens = max(0, baseline_tokens - indexed_tokens)
    saved_percent = round((saved_tokens / baseline_tokens) * 100, 2) if baseline_tokens else 0.0
    payload = {
        "repo_ref": repo_ref,
        "files": files,
        "symbols": symbols,
        "stats": {
            "file_count": len(files),
            "symbol_count": len(symbols),
        },
        "token_savings_estimate": {
            "baseline_tokens_est": baseline_tokens,
            "indexed_tokens_est": indexed_tokens,
            "saved_tokens_est": saved_tokens,
            "saved_percent_est": saved_percent,
            "method": "heuristic",
            "confidence": "low",
        },
    }
    if isinstance(index_meta, dict) and index_meta:
        payload["index_meta"] = index_meta
    return payload


def search_symbols(payload: dict[str, Any], query: str, max_results: int = 20) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    symbols = payload.get("symbols", [])
    scored: list[tuple[int, dict[str, Any]]] = []
    for sym in symbols:
        name = str(sym.get("name", "")).lower()
        signature = str(sym.get("signature", "")).lower()
        score = 0
        if name == needle:
            score += 20
        elif needle in name:
            score += 10
        if needle in signature:
            score += 6
        if score > 0:
            scored.append((score, sym))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_results]]


def get_symbol(payload: dict[str, Any], symbol_id: str) -> dict[str, Any] | None:
    symbols = payload.get("symbols", [])
    files = payload.get("files", [])
    files_by_path = {str(f.get("path", "")): f for f in files}
    for sym in symbols:
        if sym.get("id") == symbol_id:
            file_meta = files_by_path.get(str(sym.get("file", "")), {})
            return {
                "symbol": sym,
                "file_meta": {
                    "path": file_meta.get("path"),
                    "language": file_meta.get("language"),
                    "line_count": file_meta.get("line_count"),
                    "approx_tokens": file_meta.get("approx_tokens"),
                },
            }
    return None


def get_outline(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files", [])
    files_by_path = {str(f.get("path", "")): f for f in files}
    by_file: dict[str, list[dict[str, Any]]] = {}
    for sym in payload.get("symbols", []):
        file = str(sym.get("file", ""))
        entry: dict[str, Any] = {
            "id": sym.get("id"),
            "kind": sym.get("kind"),
            "name": sym.get("name"),
            "line": sym.get("line"),
        }
        # Include Solidity-specific fields when present
        for extra_key in ("visibility", "reachable", "payable"):
            if extra_key in sym:
                entry[extra_key] = sym[extra_key]
        by_file.setdefault(file, []).append(entry)
    file_items = []
    for file, symbols in sorted(by_file.items()):
        meta = files_by_path.get(file, {})
        file_items.append(
            {
                "file": file,
                "language": meta.get("language"),
                "line_count": meta.get("line_count"),
                "symbol_count": len(symbols),
                "symbols": symbols,
            }
        )
    return {
        "summary": {
            "file_count": len(files),
            "file_count_with_symbols": len(file_items),
            "symbol_count": len(payload.get("symbols", [])),
        },
        "files": file_items,
    }
