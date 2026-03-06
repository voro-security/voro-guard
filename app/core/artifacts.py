from __future__ import annotations

from pathlib import Path
from typing import Any, Tuple
import json
import re

from app.config import settings
from app.core.signing import canonical_json, sha256_hex, verify_signature

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._:-]+$")


def _sanitize_component(value: str) -> str:
    if not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError("artifact_invalid")
    return value.replace(":", "_")


def _artifact_root() -> Path:
    root = Path(settings.artifact_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_filename(workspace_id: str, repo_fingerprint: str, artifact_id: str) -> str:
    ws = _sanitize_component(workspace_id)
    rf = _sanitize_component(repo_fingerprint)
    aid = _sanitize_component(artifact_id)
    return f"{ws}__{rf}__{aid}.json"


def artifact_path(workspace_id: str, repo_fingerprint: str, artifact_id: str) -> Path:
    root = _artifact_root()
    filename = artifact_filename(workspace_id, repo_fingerprint, artifact_id)
    path = (root / filename).resolve()
    if root not in path.parents and path != root:
        raise ValueError("artifact_path_outside_root")
    return path


def persist_artifact(envelope: dict[str, Any]) -> str:
    path = artifact_path(
        str(envelope["workspace_id"]),
        str(envelope["repo_fingerprint"]),
        str(envelope["artifact_id"]),
    )
    path.write_text(json.dumps(envelope, sort_keys=True, indent=2), encoding="utf-8")
    return str(path)


def load_artifact(workspace_id: str, repo_fingerprint: str, artifact_id: str) -> dict[str, Any] | None:
    path = artifact_path(workspace_id, repo_fingerprint, artifact_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_latest_artifact(workspace_id: str, artifact_id: str) -> dict[str, Any] | None:
    root = _artifact_root()
    ws = _sanitize_component(workspace_id)
    aid = _sanitize_component(artifact_id)
    pattern = f"{ws}__*__{aid}.json"
    matches = sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in matches:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def _unsigned_subset(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": artifact.get("schema_version", "c35-v1"),
        "workspace_id": artifact.get("workspace_id", ""),
        "source_type": artifact.get("source_type", ""),
        "source_id": artifact.get("source_id", ""),
        "source_revision": artifact.get("source_revision", ""),
        "source_fingerprint": artifact.get("source_fingerprint", artifact.get("repo_fingerprint", "")),
        "repo_fingerprint": artifact.get("repo_fingerprint", ""),
        "artifact_id": artifact.get("artifact_id", ""),
        "artifact_version": artifact.get("artifact_version", 1),
        "rebuild_reason": artifact.get("rebuild_reason", "full_rebuild_first_index"),
        "payload": artifact.get("payload", {}),
    }


def verify_artifact(
    artifact: dict[str, Any],
    workspace_id: str,
    source_fingerprint: str,
    artifact_id: str,
) -> Tuple[bool, str, str]:
    if not artifact:
        return False, "artifact_invalid", "artifact payload missing"

    # D1 identity checks
    if (
        artifact.get("workspace_id") != workspace_id
        or artifact.get("source_fingerprint", artifact.get("repo_fingerprint")) != source_fingerprint
        or artifact.get("artifact_id") != artifact_id
    ):
        return False, "artifact_identity_mismatch", "artifact identity mismatch"

    manifest = artifact.get("manifest")
    stored_hash = artifact.get("artifact_hash")
    if not isinstance(manifest, dict) or not isinstance(stored_hash, str):
        return False, "artifact_untrusted_missing_manifest", "manifest/hash missing"

    signature = manifest.get("signature")
    if not isinstance(signature, str) or not signature.strip():
        if settings.trust_mode == "legacy":
            return True, "code_index_success", "legacy_unverified"
        return False, "artifact_untrusted_missing_manifest", "signature missing"

    recomputed_hash = sha256_hex(canonical_json(_unsigned_subset(artifact)))
    if recomputed_hash != stored_hash:
        return False, "artifact_untrusted_hash_mismatch", "artifact hash mismatch"

    if not settings.signing_key:
        if settings.trust_mode == "legacy":
            return True, "code_index_success", "legacy_unverified"
        return False, "artifact_untrusted_signature_invalid", "signing key not configured"

    if not verify_signature(stored_hash, signature, settings.signing_key):
        return False, "artifact_untrusted_signature_invalid", "invalid signature"

    return True, "code_index_success", "trusted"
