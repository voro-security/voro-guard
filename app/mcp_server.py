"""
MCP wrapper for voro-guard.

Exposes the index-guard HTTP API as MCP tools via FastMCP (stdio transport).
Can operate in two modes:
  1. Managed mode (default): starts the FastAPI server as a child subprocess,
     then proxies MCP tool calls to it. The subprocess is torn down on exit.
  2. External mode (INDEX_GUARD_URL env var set): connects to an already-running
     instance without managing its lifecycle.

Entry point:
    python -m app.mcp_server
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastmcp import FastMCP

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


def _start_managed_server() -> None:
    """Start the FastAPI server as a subprocess on _MANAGED_PORT."""
    global _managed_proc
    if _managed_proc is not None:
        return

    env = os.environ.copy()
    env["UVICORN_PORT"] = str(_MANAGED_PORT)  # passed via CLI below

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
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


def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST to the FastAPI service and return the JSON response."""
    url = f"{INDEX_GUARD_URL}{path}"
    try:
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
    name="voro-guard",
    instructions=(
        "Code symbol index for voro-guard. "
        "Use search_symbols to find functions/classes by name, "
        "get_symbol to retrieve full details for a specific symbol ID, "
        "outline_file to list all symbols in a repository artifact, "
        "and index_repo to trigger indexing of a repository."
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
