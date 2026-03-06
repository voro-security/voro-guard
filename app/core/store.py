from __future__ import annotations

from typing import Any


def build_index_payload(repo_ref: str, files: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> dict[str, Any]:
    baseline_tokens = sum(int(f.get("approx_tokens", 0)) for f in files)
    indexed_tokens = min(baseline_tokens, max(0, len(symbols) * 60 + len(files) * 20))
    saved_tokens = max(0, baseline_tokens - indexed_tokens)
    saved_percent = round((saved_tokens / baseline_tokens) * 100, 2) if baseline_tokens else 0.0
    return {
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
    for sym in symbols:
        if sym.get("id") == symbol_id:
            return sym
    return None


def get_outline(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_file: dict[str, list[dict[str, Any]]] = {}
    for sym in payload.get("symbols", []):
        file = str(sym.get("file", ""))
        by_file.setdefault(file, []).append(
            {
                "id": sym.get("id"),
                "kind": sym.get("kind"),
                "name": sym.get("name"),
                "line": sym.get("line"),
            }
        )
    return [{"file": file, "symbols": items} for file, items in sorted(by_file.items())]

