import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from fastapi import HTTPException

from app.config import settings
from app.core.artifacts import load_artifact, persist_artifact, verify_artifact
from app.core.docs_store import build_docs_payload
from app.core.signing import canonical_json, sha256_hex, sign_hash
from app.models.schemas import ArtifactEnvelope, GetRequest, Manifest, OutlineRequest, SearchRequest
from app.routes.query import get_outline, get_symbol, search_index


def setup_function() -> None:
    settings.trust_mode = "strict"
    settings.signing_key = "dev-signing-key"


def _docs_envelope(tmp_path: Path) -> dict:
    settings.artifact_root = str(tmp_path / "artifacts")
    payload = build_docs_payload(
        "repo",
        [
            {
                "document": {
                    "doc_id": "doc-1",
                    "path": "README.md",
                    "title": "",
                    "status": "unknown",
                    "class": "unknown",
                    "authority": "unknown",
                    "generator": "unknown",
                    "editing_rule": "unknown",
                    "visibility": "public",
                    "visibility_source": "default_visibility",
                    "section_count": 1,
                },
                "sections": [
                    {
                        "section_id": "sec-1",
                        "doc_id": "doc-1",
                        "heading": "Intro",
                        "heading_level": 1,
                        "heading_path": ["Intro"],
                        "start_line": 1,
                        "end_line": 3,
                        "summary": "Intro section.",
                        "keywords": ["intro", "section"],
                        "visibility": "public",
                    }
                ],
            }
        ],
    )
    unsigned = {
        "schema_version": "docs-v1",
        "workspace_id": "ws1",
        "source_type": "local_repo",
        "source_id": "repo",
        "source_revision": "r1",
        "source_fingerprint": "sha256:docs",
        "repo_fingerprint": "sha256:docs",
        "artifact_id": "docsartifact000001",
        "artifact_version": 1,
        "rebuild_reason": "full_rebuild_first_index",
        "payload": payload,
    }
    artifact_hash = sha256_hex(canonical_json(unsigned))
    signature = sign_hash(artifact_hash, settings.signing_key)
    envelope = ArtifactEnvelope(
        schema_version="docs-v1",
        workspace_id="ws1",
        source_type="local_repo",
        source_id="repo",
        source_revision="r1",
        source_fingerprint="sha256:docs",
        repo_fingerprint="sha256:docs",
        artifact_id="docsartifact000001",
        artifact_version=1,
        rebuild_reason="full_rebuild_first_index",
        artifact_hash=artifact_hash,
        manifest=Manifest(
            signer=settings.signer,
            signed_at="2026-03-13T00:00:00+00:00",
            signature=signature,
            key_id=None,
        ),
        payload=payload,
    )
    return envelope.model_dump()


def test_docs_artifact_trust_round_trip(tmp_path: Path) -> None:
    envelope = _docs_envelope(tmp_path)
    persist_artifact(envelope)
    loaded = load_artifact("ws1", "sha256:docs", "docsartifact000001")
    assert loaded is not None

    ok, reason_code, trust_status = verify_artifact(
        loaded,
        "ws1",
        "sha256:docs",
        "docsartifact000001",
    )
    assert ok is True
    assert reason_code == "code_index_success"
    assert trust_status == "trusted"


def test_docs_artifact_tamper_fails_hash_verification(tmp_path: Path) -> None:
    envelope = _docs_envelope(tmp_path)
    persist_artifact(envelope)
    loaded = load_artifact("ws1", "sha256:docs", "docsartifact000001")
    assert loaded is not None
    loaded["payload"]["sections"][0]["summary"] = "tampered"
    persist_artifact(loaded)
    tampered = load_artifact("ws1", "sha256:docs", "docsartifact000001")

    ok, reason_code, trust_status = verify_artifact(
        tampered,
        "ws1",
        "sha256:docs",
        "docsartifact000001",
    )
    assert ok is False
    assert reason_code == "artifact_untrusted_hash_mismatch"
    assert trust_status == "artifact hash mismatch"


def test_docs_query_routes_reject_tampered_artifact(tmp_path: Path) -> None:
    envelope = _docs_envelope(tmp_path)
    persist_artifact(envelope)
    loaded = load_artifact("ws1", "sha256:docs", "docsartifact000001")
    assert loaded is not None
    loaded["payload"]["sections"][0]["summary"] = "tampered"
    persist_artifact(loaded)

    with pytest.raises(HTTPException) as doc_exc:
        get_symbol(
            GetRequest(
                workspace_id="ws1",
                source_fingerprint="sha256:docs",
                artifact_id="docsartifact000001",
                doc_id="doc-1",
            )
        )
    assert doc_exc.value.status_code == 403
    assert doc_exc.value.detail["reason_code"] == "artifact_untrusted_hash_mismatch"

    with pytest.raises(HTTPException) as outline_exc:
        get_outline(
            OutlineRequest(
                workspace_id="ws1",
                source_fingerprint="sha256:docs",
                artifact_id="docsartifact000001",
                allowed_visibility=["public"],
            )
        )
    assert outline_exc.value.status_code == 403
    assert outline_exc.value.detail["reason_code"] == "artifact_untrusted_hash_mismatch"

    with pytest.raises(HTTPException) as search_exc:
        search_index(
            SearchRequest(
                workspace_id="ws1",
                source_fingerprint="sha256:docs",
                artifact_id="docsartifact000001",
                query="intro",
                allowed_visibility=["public"],
            )
        )
    assert search_exc.value.status_code == 403
    assert search_exc.value.detail["reason_code"] == "artifact_untrusted_hash_mismatch"
