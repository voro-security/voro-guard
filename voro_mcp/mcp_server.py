"""
MCP wrapper for voro-guard.

Exposes the index-guard HTTP API as MCP tools via FastMCP (stdio transport).
Can operate in two modes:
  1. Managed mode (default): starts the FastAPI server as a child subprocess,
     then proxies MCP tool calls to it. The subprocess is torn down on exit.
  2. External mode (INDEX_GUARD_URL env var set): connects to an already-running
     instance without managing its lifecycle.

Entry point:
    python -m voro_mcp.mcp_server
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
try:
    from fastmcp import FastMCP
except ImportError:  # pragma: no cover - test/dev fallback when FastMCP is unavailable
    class FastMCP:  # type: ignore[override]
        def __init__(self, name: str, instructions: str, lifespan: Any) -> None:
            self.name = name
            self.instructions = instructions
            self.lifespan = lifespan

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self, transport: str = "stdio") -> None:
            raise RuntimeError("FastMCP is not installed")

logger = logging.getLogger("voro-guard.mcp")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# URL of the running FastAPI service. Override to skip managed subprocess mode.
_DEFAULT_BASE_URL = "http://127.0.0.1:18765"
INDEX_GUARD_URL: str = os.getenv("INDEX_GUARD_URL", _DEFAULT_BASE_URL).rstrip("/")

# Bearer token for the HTTP service (matches CODE_INDEX_SERVICE_TOKEN).
INDEX_GUARD_TOKEN: str = os.getenv("INDEX_GUARD_TOKEN", os.getenv("CODE_INDEX_SERVICE_TOKEN", ""))

# Internal port used when the MCP server starts FastAPI itself.
_MANAGED_PORT: int = int(os.getenv("INDEX_GUARD_MANAGED_PORT", "18765"))

# Maximum seconds to wait for the managed FastAPI server to become ready.
_STARTUP_TIMEOUT: int = int(os.getenv("INDEX_GUARD_STARTUP_TIMEOUT", "15"))


# ---------------------------------------------------------------------------
# Managed subprocess lifecycle
# ---------------------------------------------------------------------------

_managed_proc: subprocess.Popen | None = None


def _build_auth_headers() -> dict[str, str]:
    if INDEX_GUARD_TOKEN:
        return {"Authorization": f"Bearer {INDEX_GUARD_TOKEN}"}
    return {}


def _default_managed_artifact_root() -> str:
    override = os.getenv("VORO_MCP_STATE_DIR", "").strip()
    if override:
        base = Path(override).expanduser()
    else:
        xdg_state_home = os.getenv("XDG_STATE_HOME", "").strip()
        if xdg_state_home:
            base = Path(xdg_state_home).expanduser() / "voro-mcp"
        else:
            base = Path.home() / ".local" / "state" / "voro-mcp"
    return str((base / "artifacts").resolve())


def _start_managed_server() -> None:
    """Start the FastAPI server as a subprocess on _MANAGED_PORT."""
    global _managed_proc
    if _managed_proc is not None:
        return

    env = os.environ.copy()
    env["UVICORN_PORT"] = str(_MANAGED_PORT)  # passed via CLI below
    env.setdefault("ARTIFACT_ROOT", _default_managed_artifact_root())

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "voro_mcp.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(_MANAGED_PORT),
        "--log-level",
        "warning",
    ]
    logger.info("Starting managed index-guard server: %s", " ".join(cmd))
    _managed_proc = subprocess.Popen(
        cmd,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait until the health endpoint responds.
    deadline = time.monotonic() + _STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{INDEX_GUARD_URL}/health", timeout=1.0)
            if resp.status_code == 200:
                logger.info("Managed index-guard server is ready.")
                return
        except httpx.TransportError:
            pass
        time.sleep(0.25)

    # Server didn't start in time — kill it and abort.
    _managed_proc.terminate()
    _managed_proc = None
    raise RuntimeError(
        f"index-guard FastAPI server did not become ready within {_STARTUP_TIMEOUT}s"
    )


def _stop_managed_server() -> None:
    """Gracefully stop the managed subprocess."""
    global _managed_proc
    if _managed_proc is None:
        return
    try:
        _managed_proc.send_signal(signal.SIGTERM)
        _managed_proc.wait(timeout=5)
    except Exception:
        try:
            _managed_proc.kill()
        except Exception:
            pass
    _managed_proc = None


# ---------------------------------------------------------------------------
# HTTP client helper
# ---------------------------------------------------------------------------


def _request(method: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send an HTTP request to the FastAPI service and return the JSON response."""
    url = f"{INDEX_GUARD_URL}{path}"
    try:
        request = method.strip().upper()
        if request == "GET":
            resp = httpx.get(url, params=params, headers=_build_auth_headers(), timeout=30.0)
        else:
            resp = httpx.post(url, json=body, headers=_build_auth_headers(), timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        # Surface the reason_code from the error body when available.
        try:
            detail = exc.response.json()
            reason = detail.get("reason_code") or detail.get("detail", str(exc))
        except Exception:
            reason = str(exc)
        raise RuntimeError(f"index-guard error ({exc.response.status_code}): {reason}") from exc
    except httpx.TransportError as exc:
        raise RuntimeError(f"index-guard unreachable: {exc}") from exc


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    return _request("POST", path, body=body)


def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    return _request("GET", path, params=params)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify_component(value: str) -> str:
    lowered = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    compact = "-".join(part for part in lowered.split("-") if part)
    return compact or "unknown"


def _work_state_source_id(
    *,
    agent_id: str,
    workspace_root: str,
    repo: str,
    worktree_path: str,
) -> str:
    identity = f"{workspace_root}:{repo}:{worktree_path}:{agent_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"work-state:{_slugify_component(agent_id)}:{_slugify_component(repo)}:{digest}"


# ---------------------------------------------------------------------------
# MCP server + lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: FastMCP):
    """Start the managed FastAPI server if INDEX_GUARD_URL is the default."""
    manage = os.getenv("INDEX_GUARD_URL") is None  # only manage when URL not overridden
    if manage:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _start_managed_server)
    try:
        yield
    finally:
        if manage:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _stop_managed_server)


mcp = FastMCP(
    name="io.github.voro-security/voro-mcp",
    instructions=(
        "Code intelligence and signed artifact retrieval for voro-guard. "
        "Use search_symbols to find functions/classes by name, "
        "get_symbol to retrieve full details for a specific symbol ID, "
        "outline_file to list all symbols in a repository artifact, "
        "and index_repo to trigger indexing of a repository. "
        "For docs artifacts, use index_docs, search_docs, get_doc_section, and outline_docs. "
        "For adaptive learning backplane state, use publish_learning_state, publish_work_state, read_learning_state, and list_learning_states. "
        "For the derived GitHub governance drift report, use read_governance_report and list_governance_reports. "
        "For session resume after compaction, use hydrate_session."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search_symbols(
    query: str,
    workspace_id: str,
    artifact_id: str,
    source_fingerprint: str = "",
) -> dict[str, Any]:
    """
    Search for symbols (functions, classes, etc.) in an indexed repository artifact.

    Args:
        query: Name or partial name to search for.
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Artifact identifier returned by index_repo.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.
            Required unless repo_fingerprint is known — pass as source_fingerprint.

    Returns:
        JSON response with a 'results' list of matching symbols.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "query": query,
    }
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    return _post("/v1/search", body)


@mcp.tool()
def get_symbol(
    symbol_id: str,
    workspace_id: str,
    artifact_id: str,
    source_fingerprint: str = "",
) -> dict[str, Any]:
    """
    Retrieve full details for a specific symbol by its ID.

    Args:
        symbol_id: Unique symbol identifier (from a prior search_symbols call).
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Artifact identifier returned by index_repo.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.

    Returns:
        JSON response with 'results' containing the symbol details and file metadata.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "symbol_id": symbol_id,
    }
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    return _post("/v1/get", body)


@mcp.tool()
def outline_file(
    workspace_id: str,
    artifact_id: str,
    source_fingerprint: str = "",
) -> dict[str, Any]:
    """
    Return a structured outline of all files and symbols in an indexed artifact.

    Provides a high-level map of the repository: which files exist, what language
    each is, and the symbols (functions, classes) extracted from each file.

    Args:
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Artifact identifier returned by index_repo.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.

    Returns:
        JSON response with summary counts and a per-file list of symbols.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
    }
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    return _post("/v1/outline", body)


@mcp.tool()
def index_repo(
    source_type: str,
    source_id: str,
    workspace_id: str,
    source_revision: str = "",
) -> dict[str, Any]:
    """
    Trigger indexing of a repository and return an artifact that can be queried.

    Creates or updates a code index artifact for the specified repository.
    Subsequent calls with the same source will perform incremental updates when
    the source type supports it (github, git).

    Args:
        source_type: One of 'github', 'git', 'local_repo', 'snapshot'.
            Use 'github' for GitHub repos (source_id = 'owner/repo').
            Use 'local_repo' for local filesystem paths (source_id = absolute path).
        source_id: Repository reference — GitHub 'owner/repo' or local path.
        workspace_id: Workspace identifier to scope this artifact.
        source_revision: Optional revision/commit SHA. Omit to use latest.

    Returns:
        JSON response including 'artifact_id' and 'source_fingerprint' needed
        for subsequent search_symbols / get_symbol / outline_file calls.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "source_type": source_type,
        "source_id": source_id,
    }
    if source_revision:
        body["source_revision"] = source_revision
    return _post("/v1/index", body)


@mcp.tool()
def index_docs(
    source_type: str,
    source_id: str,
    workspace_id: str,
    source_revision: str = "",
) -> dict[str, Any]:
    """
    Trigger docs indexing and return a signed docs artifact.

    Args:
        source_type: One of 'github', 'git', 'local_repo', 'snapshot'.
        source_id: Repository reference — GitHub 'owner/repo' or local path.
        workspace_id: Workspace identifier to scope this artifact.
        source_revision: Optional revision/commit SHA. Omit to use latest.

    Returns:
        JSON response including the docs artifact_id and source_fingerprint for
        subsequent search_docs / get_doc_section calls.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "source_type": source_type,
        "source_id": source_id,
        "index_kind": "docs",
    }
    if source_revision:
        body["source_revision"] = source_revision
    return _post("/v1/index", body)


@mcp.tool()
def search_docs(
    query: str,
    workspace_id: str,
    artifact_id: str,
    source_fingerprint: str = "",
    allowed_visibility: list[str] | None = None,
) -> dict[str, Any]:
    """
    Search a signed docs artifact using headings, summaries, and keywords.

    Args:
        query: Search term to match against docs derived fields.
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Docs artifact identifier returned by index_docs.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.
        allowed_visibility: Optional allowed document visibility tiers to filter results.

    Returns:
        JSON response with a 'results' list of matching docs sections.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "query": query,
    }
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    if allowed_visibility:
        body["allowed_visibility"] = allowed_visibility
    return _post("/v1/search", body)


@mcp.tool()
def get_doc_section(
    workspace_id: str,
    artifact_id: str,
    doc_id: str = "",
    section_id: str = "",
    source_fingerprint: str = "",
    allowed_visibility: list[str] | None = None,
) -> dict[str, Any]:
    """
    Retrieve a docs document or specific section from a signed docs artifact.

    Args:
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Docs artifact identifier returned by index_docs.
        doc_id: Optional docs document identifier.
        section_id: Optional docs section identifier.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.
        allowed_visibility: Optional allowed document visibility tiers to filter results.

    Returns:
        JSON response with 'results' containing the matched document or section.
    """
    if not doc_id and not section_id:
        raise ValueError("doc_id_or_section_id_required")

    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
    }
    if doc_id:
        body["doc_id"] = doc_id
    if section_id:
        body["section_id"] = section_id
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    if allowed_visibility:
        body["allowed_visibility"] = allowed_visibility
    return _post("/v1/get", body)


@mcp.tool()
def outline_docs(
    workspace_id: str,
    artifact_id: str,
    source_fingerprint: str = "",
    allowed_visibility: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return a structured outline of documents and sections in a signed docs artifact.

    Args:
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Docs artifact identifier returned by index_docs.
        source_fingerprint: Source fingerprint (sha256:...) from the index response.
        allowed_visibility: Optional allowed document visibility tiers to filter results.

    Returns:
        JSON response with summary counts and per-document section outlines.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
    }
    if source_fingerprint:
        body["source_fingerprint"] = source_fingerprint
    if allowed_visibility:
        body["allowed_visibility"] = allowed_visibility
    return _post("/v1/outline", body)


@mcp.tool()
def publish_learning_state(
    workspace_id: str,
    source_id: str,
    state_type: str,
    payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Publish an opaque learning-state snapshot to the adaptive learning backplane.

    Args:
        workspace_id: Workspace identifier that owns the learning state.
        source_id: Publishing source identifier, such as the producer repo or component.
        state_type: Logical learning-state type (priors, multipliers, quarantine, precision).
        payload: Opaque publisher-defined payload.
        metadata: Optional publisher-defined metadata.

    Returns:
        Signed learning-state artifact response.
    """
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "state_type": state_type,
        "payload": payload,
    }
    if metadata:
        body["metadata"] = metadata
    return _post("/v1/learning-state", body)


@mcp.tool()
def publish_work_state(
    workspace_id: str,
    current_objective: str,
    agent_id: str,
    workspace_root: str,
    repo: str,
    worktree_path: str,
    active_lane: str = "",
    recent_decisions: list[dict[str, str]] | None = None,
    open_loops: list[str] | None = None,
    do_not_redo: list[str] | None = None,
    relevant_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Publish a typed work-state.v1 artifact for session resume after compaction.

    This is a thin convenience wrapper over publish_learning_state. It does not
    introduce a new storage system or mid-session autosave behavior.
    """
    payload: dict[str, Any] = {
        "schema_version": "work-state-v1",
        "agent_id": agent_id,
        "workspace_root": workspace_root,
        "repo": repo,
        "worktree_path": worktree_path,
        "updated_at": _now_utc(),
        "current_objective": current_objective,
    }
    if active_lane:
        payload["active_lane"] = active_lane
    if recent_decisions:
        payload["recent_decisions"] = recent_decisions
    if open_loops:
        payload["open_loops"] = open_loops
    if do_not_redo:
        payload["do_not_redo"] = do_not_redo
    if relevant_refs:
        payload["relevant_refs"] = relevant_refs
    source_id = _work_state_source_id(
        agent_id=agent_id,
        workspace_root=workspace_root,
        repo=repo,
        worktree_path=worktree_path,
    )
    body: dict[str, Any] = {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "state_type": "work-state",
        "payload": payload,
    }
    if metadata:
        body["metadata"] = metadata
    return _post("/v1/learning-state", body)


@mcp.tool()
def read_learning_state(
    workspace_id: str,
    artifact_id: str,
) -> dict[str, Any]:
    """
    Read the latest signed learning-state artifact for a given artifact ID.

    Args:
        workspace_id: Workspace identifier that owns the artifact.
        artifact_id: Stable learning-state artifact identifier.

    Returns:
        JSON response containing the signed learning-state envelope.
    """
    return _get("/v1/learning-state/" + artifact_id, {"workspace_id": workspace_id})


@mcp.tool()
def list_learning_states(
    workspace_id: str,
    source_id: str = "",
    state_type: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    """
    List the latest learning-state artifacts for a workspace, optionally filtered.

    Args:
        workspace_id: Workspace identifier that owns the artifacts.
        source_id: Optional producer identifier filter.
        state_type: Optional logical learning-state type filter.
        limit: Maximum number of items to return.

    Returns:
        JSON response with learning-state summaries.
    """
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "limit": limit,
    }
    if source_id:
        params["source_id"] = source_id
    if state_type:
        params["state_type"] = state_type
    return _get("/v1/learning-states", params)


@mcp.tool()
def read_governance_report(
    workspace_id: str,
    source_id: str = "github-governance",
) -> dict[str, Any]:
    """
    Read the latest published GitHub governance drift report.

    Args:
        workspace_id: Workspace identifier that owns the artifact.
        source_id: Governance report source identifier. Defaults to the fleet governance source.

    Returns:
        JSON response containing the signed governance report envelope.
    """
    params: dict[str, Any] = {"workspace_id": workspace_id, "source_id": source_id}
    return _get("/v1/governance-report", params)


@mcp.tool()
def list_governance_reports(
    workspace_id: str,
    source_id: str = "github-governance",
    limit: int = 20,
) -> dict[str, Any]:
    """
    List published GitHub governance drift report summaries.

    Args:
        workspace_id: Workspace identifier that owns the artifacts.
        source_id: Governance report source identifier. Defaults to the fleet governance source.
        limit: Maximum number of items to return.

    Returns:
        JSON response with governance report summaries.
    """
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "source_id": source_id,
        "limit": limit,
    }
    return _get("/v1/governance-reports", params)


@mcp.tool()
def hydrate_session(
    workspace_id: str,
    agent_id: str = "",
    repo: str = "",
    worktree_path: str = "",
) -> dict[str, Any]:
    """
    Resume a session after compaction by assembling signed state artifacts.

    Returns system-state, repo-state(s), and work-state with freshness
    calculation. Falls back gracefully when state is missing or stale.

    Args:
        workspace_id: Workspace identifier for state lookup.
        agent_id: Optional agent identifier for work-state matching.
        repo: Optional repo name to filter repo-states and work-state.
        worktree_path: Optional worktree path for work-state identity.

    Returns:
        Hydration response with freshness_status, assembled states,
        read_next pointers, and warnings.
    """
    params: dict[str, Any] = {"workspace_id": workspace_id}
    if agent_id:
        params["agent_id"] = agent_id
    if repo:
        params["repo"] = repo
    if worktree_path:
        params["worktree_path"] = worktree_path
    return _get("/v1/hydrate", params)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
