"""Background polling loop for auto-fresh indexing.

Periodically checks GitHub HEAD SHA for configured repos and triggers
re-indexing via the existing create_index route when changes are detected.
Feature-gated: CODE_INDEX_POLLER_ENABLED=1 to activate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.core.artifacts import load_latest_artifact
from app.core.identity import compute_artifact_identity
from app.core.indexer import _github_headers
from app.models.schemas import IndexRequest
from app.routes.index import create_index

logger = logging.getLogger("voro-guard.poller")

MAX_JITTER_SECONDS = 30
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 600


class RepoPoller:
    """Polls GitHub repos for HEAD changes and triggers re-indexing."""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._repos: list[dict[str, Any]] = []
        self._tasks: list[asyncio.Task] = []
        self._load_config()

    def _load_config(self) -> None:
        try:
            data = json.loads(self._config_path.read_text(encoding="utf-8"))
            self._repos = data.get("repos", [])
            logger.info("Poller config loaded: %d repos from %s", len(self._repos), self._config_path)
        except FileNotFoundError:
            logger.warning("Poller config not found: %s — polling disabled", self._config_path)
            self._repos = []
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Poller config invalid: %s — %s", self._config_path, exc)
            self._repos = []

    async def start(self) -> None:
        for entry in self._repos:
            task = asyncio.create_task(self._poll_repo(entry))
            self._tasks.append(task)
        if self._tasks:
            logger.info("Poller started: %d repo tasks", len(self._tasks))

    async def _poll_repo(self, entry: dict[str, Any]) -> None:
        source_id = entry.get("source_id", "")
        interval = max(60, int(entry.get("interval_seconds", 300)))
        workspace_id = entry.get("workspace_id", "voro")
        source_type = entry.get("source_type", "github")
        consecutive_errors = 0

        # Stagger initial poll to avoid thundering herd
        jitter = random.uniform(0, MAX_JITTER_SECONDS)
        await asyncio.sleep(jitter)

        while True:
            try:
                owner, repo = source_id.split("/", 1)
                head_sha = await self._fetch_head_sha(owner, repo)
                if head_sha is None:
                    logger.warning("Poller: could not fetch HEAD for %s", source_id)
                    consecutive_errors += 1
                    backoff = min(BACKOFF_BASE_SECONDS * consecutive_errors, BACKOFF_MAX_SECONDS)
                    await asyncio.sleep(backoff)
                    continue

                artifact_id = compute_artifact_identity(workspace_id, source_type, source_id)
                latest = load_latest_artifact(workspace_id, artifact_id)
                stored_revision = latest.get("source_revision", "") if latest else ""

                if stored_revision == head_sha:
                    logger.debug("Poller: %s is fresh (SHA %s)", source_id, head_sha[:8])
                else:
                    logger.info("Poller: %s changed %s → %s — triggering re-index",
                                source_id, stored_revision[:8] if stored_revision else "none", head_sha[:8])
                    await self._trigger_reindex(entry, head_sha)

                consecutive_errors = 0
            except asyncio.CancelledError:
                logger.info("Poller: task cancelled for %s", source_id)
                return
            except Exception:
                consecutive_errors += 1
                logger.exception("Poller: error polling %s (attempt %d)", source_id, consecutive_errors)
                backoff = min(BACKOFF_BASE_SECONDS * consecutive_errors, BACKOFF_MAX_SECONDS)
                await asyncio.sleep(backoff)
                continue

            await asyncio.sleep(interval)

    async def _fetch_head_sha(self, owner: str, repo: str) -> str | None:
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/HEAD"
        headers = _github_headers()
        headers["Accept"] = "application/vnd.github.sha"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return resp.text.strip()
                logger.warning("Poller: HEAD fetch for %s/%s returned %d", owner, repo, resp.status_code)
                return None
        except httpx.HTTPError as exc:
            logger.warning("Poller: HEAD fetch failed for %s/%s — %s", owner, repo, exc)
            return None

    async def _trigger_reindex(self, entry: dict[str, Any], sha: str) -> None:
        req = IndexRequest(
            workspace_id=entry.get("workspace_id", "voro"),
            source_type=entry.get("source_type", "github"),
            source_id=entry.get("source_id", ""),
            source_revision=sha,
            repo_ref=entry.get("source_id", ""),
        )
        try:
            result = await asyncio.to_thread(create_index, req)
            reason = result.get("rebuild_reason", "unknown") if isinstance(result, dict) else "unknown"
            logger.info("Poller: re-index complete for %s — %s", entry.get("source_id"), reason)
        except Exception:
            logger.exception("Poller: re-index failed for %s", entry.get("source_id"))

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("Poller stopped")
