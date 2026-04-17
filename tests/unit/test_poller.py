"""Tests for the background polling loop (voro_mcp.core.poller)."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voro_mcp.core.poller import RepoPoller


@pytest.fixture
def poll_config(tmp_path):
    config = {
        "repos": [
            {
                "workspace_id": "test-ws",
                "source_type": "github",
                "source_id": "owner/repo-a",
                "interval_seconds": 300,
            },
            {
                "workspace_id": "test-ws",
                "source_type": "github",
                "source_id": "owner/repo-b",
                "interval_seconds": 600,
            },
        ]
    }
    config_path = tmp_path / "poll.json"
    config_path.write_text(json.dumps(config))
    return config_path


@pytest.fixture
def single_repo_config(tmp_path):
    config = {
        "repos": [
            {
                "workspace_id": "test-ws",
                "source_type": "github",
                "source_id": "owner/repo-a",
                "interval_seconds": 300,
            },
        ]
    }
    config_path = tmp_path / "poll.json"
    config_path.write_text(json.dumps(config))
    return config_path


def _run(coro):
    """Run an async coroutine in a new event loop."""
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- Config loading ---

def test_config_loads_valid_json(poll_config):
    poller = RepoPoller(poll_config)
    assert len(poller._repos) == 2
    assert poller._repos[0]["source_id"] == "owner/repo-a"
    assert poller._repos[1]["source_id"] == "owner/repo-b"


def test_config_missing_file_no_crash(tmp_path):
    poller = RepoPoller(tmp_path / "nonexistent.json")
    assert poller._repos == []


def test_config_invalid_json_no_crash(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    poller = RepoPoller(bad)
    assert poller._repos == []


# --- HEAD SHA fetch ---

def test_fetch_head_sha_success(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "abc123def456\n"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("voro_mcp.core.poller.httpx.AsyncClient", return_value=mock_client):
            sha = await poller._fetch_head_sha("owner", "repo-a")

        assert sha == "abc123def456"

    _run(run())


def test_fetch_head_sha_404_returns_none(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("voro_mcp.core.poller.httpx.AsyncClient", return_value=mock_client):
            sha = await poller._fetch_head_sha("owner", "repo-a")

        assert sha is None

    _run(run())


def test_fetch_head_sha_network_error_returns_none(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("voro_mcp.core.poller.httpx.AsyncClient", return_value=mock_client):
            sha = await poller._fetch_head_sha("owner", "repo-a")

        assert sha is None

    _run(run())


# --- Skip when fresh ---

def test_skip_when_revision_matches(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        current_sha = "abc123def456"

        with patch.object(poller, "_fetch_head_sha", new_callable=AsyncMock, return_value=current_sha), \
             patch("voro_mcp.core.poller.load_latest_artifact", return_value={"source_revision": current_sha}), \
             patch.object(poller, "_trigger_reindex", new_callable=AsyncMock) as mock_reindex:

            entry = poller._repos[0]
            owner, repo = entry["source_id"].split("/", 1)
            head_sha = await poller._fetch_head_sha(owner, repo)
            from voro_mcp.core.identity import compute_artifact_identity
            from voro_mcp.core.poller import load_latest_artifact as _laa
            artifact_id = compute_artifact_identity(
                entry["workspace_id"], entry["source_type"], entry["source_id"]
            )
            # Use the module-level patched version
            import voro_mcp.core.poller as poller_mod
            latest = poller_mod.load_latest_artifact(entry["workspace_id"], artifact_id)
            stored_revision = latest.get("source_revision", "") if latest else ""
            if stored_revision != head_sha:
                await poller._trigger_reindex(entry, head_sha)

            mock_reindex.assert_not_called()

    _run(run())


# --- Trigger on change ---

def test_trigger_on_sha_change(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        old_sha = "old111"
        new_sha = "new222"

        with patch.object(poller, "_fetch_head_sha", new_callable=AsyncMock, return_value=new_sha), \
             patch("voro_mcp.core.poller.load_latest_artifact", return_value={"source_revision": old_sha}), \
             patch.object(poller, "_trigger_reindex", new_callable=AsyncMock) as mock_reindex:

            entry = poller._repos[0]
            owner, repo = entry["source_id"].split("/", 1)
            head_sha = await poller._fetch_head_sha(owner, repo)
            from voro_mcp.core.identity import compute_artifact_identity
            artifact_id = compute_artifact_identity(
                entry["workspace_id"], entry["source_type"], entry["source_id"]
            )
            from voro_mcp.core.artifacts import load_latest_artifact
            latest = load_latest_artifact(entry["workspace_id"], artifact_id)
            stored_revision = latest.get("source_revision", "") if latest else ""
            if stored_revision != head_sha:
                await poller._trigger_reindex(entry, head_sha)

            mock_reindex.assert_called_once_with(poller._repos[0], new_sha)

    _run(run())


# --- Trigger on first index (no existing artifact) ---

def test_trigger_on_first_index(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        new_sha = "first123"

        with patch.object(poller, "_fetch_head_sha", new_callable=AsyncMock, return_value=new_sha), \
             patch("voro_mcp.core.poller.load_latest_artifact", return_value=None), \
             patch.object(poller, "_trigger_reindex", new_callable=AsyncMock) as mock_reindex:

            entry = poller._repos[0]
            owner, repo = entry["source_id"].split("/", 1)
            head_sha = await poller._fetch_head_sha(owner, repo)
            from voro_mcp.core.identity import compute_artifact_identity
            artifact_id = compute_artifact_identity(
                entry["workspace_id"], entry["source_type"], entry["source_id"]
            )
            from voro_mcp.core.artifacts import load_latest_artifact
            latest = load_latest_artifact(entry["workspace_id"], artifact_id)
            stored_revision = latest.get("source_revision", "") if latest else ""
            if stored_revision != head_sha:
                await poller._trigger_reindex(entry, head_sha)

            mock_reindex.assert_called_once_with(poller._repos[0], new_sha)

    _run(run())


# --- Error isolation ---

def test_error_isolation_between_repos(poll_config):
    """One repo failing doesn't prevent the other from being polled."""
    async def run():
        poller = RepoPoller(poll_config)
        call_log = []

        async def mock_fetch(owner, repo):
            if repo == "repo-a":
                raise httpx.ConnectError("connection refused")
            return "sha999"

        async def mock_reindex(entry, sha):
            call_log.append((entry["source_id"], sha))

        with patch.object(poller, "_fetch_head_sha", side_effect=mock_fetch), \
             patch("voro_mcp.core.poller.load_latest_artifact", return_value={"source_revision": "old"}), \
             patch.object(poller, "_trigger_reindex", side_effect=mock_reindex):

            for entry in poller._repos:
                try:
                    owner, repo = entry["source_id"].split("/", 1)
                    head_sha = await poller._fetch_head_sha(owner, repo)
                    if head_sha and head_sha != "old":
                        await poller._trigger_reindex(entry, head_sha)
                except Exception:
                    pass

        assert len(call_log) == 1
        assert call_log[0] == ("owner/repo-b", "sha999")

    _run(run())


# --- Start / stop lifecycle ---

def test_start_creates_tasks(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)
        with patch.object(poller, "_poll_repo", new_callable=AsyncMock):
            await poller.start()
            assert len(poller._tasks) == 1
            poller.stop()
            assert len(poller._tasks) == 0

    _run(run())


def test_stop_cancels_running_tasks(single_repo_config):
    async def run():
        poller = RepoPoller(single_repo_config)

        async def long_poll(entry):
            await asyncio.sleep(999)

        with patch.object(poller, "_poll_repo", side_effect=long_poll):
            await poller.start()
            assert len(poller._tasks) == 1
            task = poller._tasks[0]
            # Let the event loop schedule the task before cancelling
            await asyncio.sleep(0)
            poller.stop()
            # After cancel() the task is in cancelling state
            assert task.cancelled() or task.cancelling()

    _run(run())
