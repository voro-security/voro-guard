from __future__ import annotations

from hashlib import sha256
import re

ALLOWED_VISIBILITY = {"public", "pro", "enterprise", "internal"}
_HEADER_KEYS = {
    "status": "status",
    "class": "class",
    "authority": "authority",
    "generator": "generator",
    "editing rule": "editing_rule",
    "editing_rule": "editing_rule",
}
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _parse_frontmatter(lines: list[str]) -> tuple[dict[str, object], int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0

    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
    if end_idx == -1:
        return {}, 0

    data: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in lines[1:end_idx]:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key:
            value = _strip_quotes(stripped[2:].strip())
            current = data.setdefault(current_list_key, [])
            if isinstance(current, list):
                current.append(value)
            continue
        if ":" not in line:
            current_list_key = None
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            current_list_key = None
            continue
        if value == "":
            data[key] = []
            current_list_key = key
            continue
        data[key] = _strip_quotes(value)
        current_list_key = None
    return data, end_idx + 1


def _parse_voro_headers(lines: list[str], start_idx: int) -> tuple[dict[str, str], int]:
    metadata: dict[str, str] = {}
    idx = start_idx
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        normalized = stripped[2:].strip() if stripped.startswith("# ") else stripped
        if ":" not in normalized:
            break
        key, value = normalized.split(":", 1)
        mapped_key = _HEADER_KEYS.get(key.strip().lower())
        if not mapped_key:
            break
        metadata[mapped_key] = value.strip()
        idx += 1
    return metadata, idx


def _heading_match(line: str) -> re.Match[str] | None:
    return re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)


def _section_id(path: str, heading_path: list[str], start_line: int) -> str:
    base = f"{path}|{'/'.join(heading_path) or '__document__'}|{start_line}"
    return sha256(base.encode("utf-8")).hexdigest()[:16]


def _summarize(lines: list[str]) -> str:
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                break
            continue
        if _heading_match(stripped):
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)[:200]


def _keywords(heading_path: list[str], summary: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    text = " ".join(heading_path + [summary])
    for token in re.findall(r"[A-Za-z0-9_]+", text.lower()):
        if token in _STOP_WORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def parse_markdown_document(
    relative_path: str,
    content: str,
    default_visibility: str = "public",
) -> dict[str, object]:
    if default_visibility not in ALLOWED_VISIBILITY:
        raise ValueError("visibility_invalid")

    lines = content.splitlines()
    frontmatter, body_start_idx = _parse_frontmatter(lines)
    headers, content_start_idx = _parse_voro_headers(lines, body_start_idx)

    visibility_raw = frontmatter.get("visibility")
    if visibility_raw is None:
        visibility = default_visibility
        visibility_source = "default_visibility"
    else:
        visibility = str(visibility_raw).strip()
        if visibility not in ALLOWED_VISIBILITY:
            raise ValueError("visibility_invalid")
        visibility_source = "frontmatter"

    document = {
        "doc_id": sha256(relative_path.encode("utf-8")).hexdigest()[:16],
        "path": relative_path,
        "title": str(frontmatter.get("title", "")).strip(),
        "status": headers.get("status", "unknown"),
        "class": headers.get("class", "unknown"),
        "authority": headers.get("authority", "unknown"),
        "generator": headers.get("generator", "unknown"),
        "editing_rule": headers.get("editing_rule", "unknown"),
        "visibility": visibility,
        "visibility_source": visibility_source,
    }

    sections: list[dict[str, object]] = []
    stack: list[str] = []
    current_heading: str | None = None
    current_level: int | None = None
    current_path: list[str] = []
    current_start_line: int | None = None
    current_body_lines: list[str] = []

    def flush(end_line: int) -> None:
        nonlocal current_heading, current_level, current_path, current_start_line, current_body_lines
        if current_start_line is None:
            return
        summary = _summarize(current_body_lines)
        sections.append(
            {
                "section_id": _section_id(relative_path, current_path, current_start_line),
                "doc_id": document["doc_id"],
                "heading": current_heading or "",
                "heading_level": current_level or 0,
                "heading_path": list(current_path),
                "start_line": current_start_line,
                "end_line": end_line,
                "summary": summary,
                "keywords": _keywords(current_path, summary),
                "visibility": visibility,
            }
        )
        current_heading = None
        current_level = None
        current_path = []
        current_start_line = None
        current_body_lines = []

    for idx in range(content_start_idx, len(lines)):
        line = lines[idx]
        match = _heading_match(line.strip())
        line_no = idx + 1
        if match:
            flush(line_no - 1)
            level = len(match.group(1))
            heading = match.group(2).strip()
            stack[:] = stack[: level - 1]
            stack.append(heading)
            current_heading = heading
            current_level = level
            current_path = list(stack)
            current_start_line = line_no
            current_body_lines = []
            continue
        if current_start_line is None:
            current_heading = ""
            current_level = 0
            current_path = []
            current_start_line = max(content_start_idx + 1, 1)
        current_body_lines.append(line)

    if current_start_line is None:
        current_start_line = max(content_start_idx + 1, 1)
        current_heading = ""
        current_level = 0
        current_path = []
    flush(len(lines) if lines else 1)

    document["section_count"] = len(sections)
    return {
        "document": document,
        "sections": sections,
    }
