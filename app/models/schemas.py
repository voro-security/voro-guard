from pydantic import BaseModel, Field
from typing import Optional, Literal, Any


class IndexRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    repo_fingerprint: str = Field(min_length=1)
    repo_ref: Optional[str] = None


class QueryRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    repo_fingerprint: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    query: Optional[str] = None
    symbol_id: Optional[str] = None
    mode: Literal["search", "get", "outline"] = "search"


class SearchRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    repo_fingerprint: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    query: str = Field(min_length=1)


class GetRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    repo_fingerprint: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    symbol_id: str = Field(min_length=1)


class OutlineRequest(BaseModel):
    workspace_id: str = Field(min_length=1)
    repo_fingerprint: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)


class Manifest(BaseModel):
    signer: str
    signed_at: str
    signature: str
    key_id: Optional[str] = None


class ArtifactEnvelope(BaseModel):
    schema_version: str = "c35-v1"
    workspace_id: str
    repo_fingerprint: str
    artifact_id: str
    artifact_hash: str
    manifest: Manifest
    payload: dict[str, Any]
