from __future__ import annotations

from app.core.signing import sha256_hex

REVISION_UNAVAILABLE = "revision:unavailable"
REPO_REF_SENTINEL = "source:unknown"
_VALID_SOURCE_TYPES = {
    "github",
    "git",
    "local_repo",
    "http_docs",
    "feed",
    "snapshot",
    "learning_state",
}


def normalize_source_fields(
    source_type: str | None,
    source_id: str | None,
    source_revision: str | None,
    repo_ref: str | None,
) -> tuple[str, str, str]:
    st = (source_type or "").strip().lower()
    sid = (source_id or "").strip()
    srev = (source_revision or "").strip()
    rref = (repo_ref or "").strip()

    if not st:
        st = "github" if rref else "snapshot"
    if st not in _VALID_SOURCE_TYPES:
        raise ValueError("source_identity_invalid")

    if not sid:
        sid = rref or REPO_REF_SENTINEL
    if not sid:
        raise ValueError("source_identity_missing")

    if not srev:
        srev = REVISION_UNAVAILABLE
    return st, sid, srev


def compute_source_fingerprint(
    workspace_id: str,
    source_type: str,
    source_id: str,
    source_revision: str,
) -> str:
    base = f"{workspace_id}:{source_type}:{source_id}:{source_revision}"
    return f"sha256:{sha256_hex(base)}"


def compute_artifact_identity(
    workspace_id: str,
    source_type: str,
    source_id: str,
    artifact_kind: str = "code",
) -> str:
    base = f"{workspace_id}:{source_type}:{source_id}"
    if artifact_kind != "code":
        base += f":{artifact_kind}"
    return sha256_hex(base)[:24]


def source_strategy(source_type: str) -> str:
    st = source_type.strip().lower()
    if st in {"github", "git", "local_repo"}:
        return "diffable"
    if st == "http_docs":
        return "conditional"
    if st == "feed":
        return "append_only"
    return "nondiffable"
