from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal, Any

from app.core.identity import (
    compute_source_fingerprint,
    normalize_source_fields,
    REPO_REF_SENTINEL,
    REVISION_UNAVAILABLE,
)


class IndexRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    index_kind: Literal["code", "docs"] = "code"
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    source_revision: Optional[str] = None
    source_fingerprint: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    repo_ref: Optional[str] = None

    @model_validator(mode="after")
    def ensure_identity(self) -> "IndexRequest":
        use_legacy_repo_fp = bool(self.repo_fingerprint) and not self.source_fingerprint
        source_type, source_id, source_revision = normalize_source_fields(
            source_type=self.source_type,
            source_id=self.source_id,
            source_revision=self.source_revision,
            repo_ref=self.repo_ref,
        )
        self.source_type = source_type
        self.source_id = source_id
        self.source_revision = source_revision
        if use_legacy_repo_fp:
            self.source_fingerprint = self.repo_fingerprint
        else:
            computed = compute_source_fingerprint(
                self.workspace_id,
                source_type,
                source_id,
                source_revision,
            )
            if self.source_fingerprint and self.source_fingerprint != computed:
                raise ValueError("source_identity_invalid")
            self.source_fingerprint = computed
        # Phase-A compatibility field; remove in C-36 Phase C.
        if not self.repo_fingerprint:
            self.repo_fingerprint = self.source_fingerprint
        if not self.repo_ref:
            self.repo_ref = source_id if source_id != REPO_REF_SENTINEL else None
        if self.source_revision is None:
            self.source_revision = REVISION_UNAVAILABLE
        return self


class QueryRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    source_revision: Optional[str] = None
    source_fingerprint: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    artifact_id: str = Field(min_length=1)
    query: Optional[str] = None
    symbol_id: Optional[str] = None
    doc_id: Optional[str] = None
    section_id: Optional[str] = None
    allowed_visibility: Optional[list[Literal["public", "pro", "enterprise", "internal"]]] = None
    mode: Literal["search", "get", "outline"] = "search"

    @model_validator(mode="after")
    def ensure_query_identity(self) -> "QueryRequest":
        if not self.source_fingerprint and not self.repo_fingerprint:
            raise ValueError("source_identity_missing")
        if not self.source_fingerprint and self.repo_fingerprint:
            self.source_fingerprint = self.repo_fingerprint
        if not self.repo_fingerprint and self.source_fingerprint:
            self.repo_fingerprint = self.source_fingerprint
        if self.source_type and not self.source_id:
            raise ValueError("source_identity_invalid")
        if self.mode == "get" and not any([self.symbol_id, self.doc_id, self.section_id]):
            raise ValueError("get_target_required")
        return self


class SearchRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    source_fingerprint: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    artifact_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    allowed_visibility: Optional[list[Literal["public", "pro", "enterprise", "internal"]]] = None

    @model_validator(mode="after")
    def compat(self) -> "SearchRequest":
        if not self.source_fingerprint and not self.repo_fingerprint:
            raise ValueError("source_identity_missing")
        if not self.source_fingerprint:
            self.source_fingerprint = self.repo_fingerprint
        if not self.repo_fingerprint:
            self.repo_fingerprint = self.source_fingerprint
        return self


class GetRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    source_fingerprint: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    artifact_id: str = Field(min_length=1)
    symbol_id: Optional[str] = None
    doc_id: Optional[str] = None
    section_id: Optional[str] = None
    allowed_visibility: Optional[list[Literal["public", "pro", "enterprise", "internal"]]] = None

    @model_validator(mode="after")
    def compat(self) -> "GetRequest":
        if not self.source_fingerprint and not self.repo_fingerprint:
            raise ValueError("source_identity_missing")
        if not self.source_fingerprint:
            self.source_fingerprint = self.repo_fingerprint
        if not self.repo_fingerprint:
            self.repo_fingerprint = self.source_fingerprint
        if not any([self.symbol_id, self.doc_id, self.section_id]):
            raise ValueError("get_target_required")
        return self


class OutlineRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    source_fingerprint: Optional[str] = None
    repo_fingerprint: Optional[str] = None
    artifact_id: str = Field(min_length=1)
    allowed_visibility: Optional[list[Literal["public", "pro", "enterprise", "internal"]]] = None

    @model_validator(mode="after")
    def compat(self) -> "OutlineRequest":
        if not self.source_fingerprint and not self.repo_fingerprint:
            raise ValueError("source_identity_missing")
        if not self.source_fingerprint:
            self.source_fingerprint = self.repo_fingerprint
        if not self.repo_fingerprint:
            self.repo_fingerprint = self.source_fingerprint
        return self


class LearningStatePublishRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    state_type: str = Field(min_length=1)
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkStateDecision(BaseModel):
    decision: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class WorkStatePayload(BaseModel):
    schema_version: Literal["work-state-v1"]
    agent_id: str = Field(min_length=1)
    workspace_root: str = Field(min_length=1)
    repo: str = Field(min_length=1)
    worktree_path: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    current_objective: str = Field(min_length=1)
    active_lane: Optional[str] = None
    recent_decisions: list[WorkStateDecision] = Field(default_factory=list)
    open_loops: list[str] = Field(default_factory=list)
    do_not_redo: list[str] = Field(default_factory=list)
    relevant_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_lists(self) -> "WorkStatePayload":
        self.open_loops = [item.strip() for item in self.open_loops if isinstance(item, str) and item.strip()]
        self.do_not_redo = [item.strip() for item in self.do_not_redo if isinstance(item, str) and item.strip()]
        self.relevant_refs = [item.strip() for item in self.relevant_refs if isinstance(item, str) and item.strip()]
        return self


class SystemStateRef(BaseModel):
    path: str = Field(min_length=1)
    role: str = Field(min_length=1)


class SystemStatePayload(BaseModel):
    schema_version: Literal["system-state-v1"]
    generated_at: str = Field(min_length=1)
    contract_path: str = Field(min_length=1)
    current_phase_focus: list[str] = Field(default_factory=list)
    phase_statuses: list[dict[str, Any]] = Field(default_factory=list)
    current_blockers: list[str] = Field(default_factory=list)
    next_recommended_lane: str = Field(min_length=1)
    follow_on_cleanup_lanes: list[str] = Field(default_factory=list)
    authoritative_refs: list[SystemStateRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_lists(self) -> "SystemStatePayload":
        self.current_phase_focus = [item.strip() for item in self.current_phase_focus if isinstance(item, str) and item.strip()]
        self.current_blockers = [item.strip() for item in self.current_blockers if isinstance(item, str) and item.strip()]
        self.follow_on_cleanup_lanes = [item.strip() for item in self.follow_on_cleanup_lanes if isinstance(item, str) and item.strip()]
        return self


class RepoStatePayload(BaseModel):
    schema_version: Literal["repo-state-v1"]
    repo: str = Field(min_length=1)
    captured_at: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)
    dirty: bool
    open_prs: list[dict[str, Any]] = Field(default_factory=list)
    important_boundaries: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_lists(self) -> "RepoStatePayload":
        self.important_boundaries = [item.strip() for item in self.important_boundaries if isinstance(item, str) and item.strip()]
        self.notes = [item.strip() for item in self.notes if isinstance(item, str) and item.strip()]
        return self


class CallgraphRequest(BaseModel):
    file: str = Field(min_length=1)
    entry_function: str = Field(min_length=1)
    max_depth: int = Field(default=10, ge=1, le=50)


class Manifest(BaseModel):
    signer: str
    signed_at: str
    signature: str
    key_id: Optional[str] = None


class ArtifactEnvelope(BaseModel):
    schema_version: str = "c35-v1"
    workspace_id: str
    source_type: str
    source_id: str
    source_revision: str
    source_fingerprint: str
    repo_fingerprint: str
    artifact_id: str
    artifact_version: int = 1
    rebuild_reason: str = "full_rebuild_first_index"
    artifact_hash: str
    manifest: Manifest
    payload: dict[str, Any]
