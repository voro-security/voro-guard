import json
import os
from pathlib import Path
import secrets

from pydantic import BaseModel


_LOCAL_MANAGED_PORT = "18765"
_LOCAL_SIGNING_STATE_PATH = Path.home() / ".claude" / "state" / "voro-guard-local-signing.json"


def _is_local_managed_guard_runtime() -> bool:
    return os.getenv("UVICORN_PORT", "").strip() == _LOCAL_MANAGED_PORT


def _load_or_create_local_managed_signing_key() -> str:
    if not _is_local_managed_guard_runtime():
        return ""

    try:
        if _LOCAL_SIGNING_STATE_PATH.is_file():
            data = json.loads(_LOCAL_SIGNING_STATE_PATH.read_text(encoding="utf-8"))
            key = str(data.get("signing_key") or "").strip()
            if key:
                return key
    except Exception:
        pass

    key = secrets.token_hex(32)
    try:
        _LOCAL_SIGNING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LOCAL_SIGNING_STATE_PATH.write_text(
            json.dumps(
                {
                    "schema_version": "voro-guard-local-signing-v1",
                    "scope": "managed-local-18765",
                    "signing_key": key,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            os.chmod(_LOCAL_SIGNING_STATE_PATH, 0o600)
        except OSError:
            pass
    except OSError:
        # Preserve strict-trust startup for managed local runtime even when
        # HOME/state storage is not writable in the current environment.
        return key
    return key


class Settings(BaseModel):
    trust_mode: str = os.getenv("CODE_INDEX_TRUST_MODE", "strict").strip().lower()
    signer: str = os.getenv("CODE_INDEX_SIGNER", "voro-index-guard").strip()
    signing_key: str = os.getenv("CODE_INDEX_SIGNING_KEY", "").strip() or _load_or_create_local_managed_signing_key()
    artifact_root: str = os.getenv("ARTIFACT_ROOT", "./data/artifacts").strip()
    adaptive_learning_enabled: bool = os.getenv("VORO_ADAPTIVE_LEARNING", "").strip().lower() in ("1", "true")
    service_token: str = os.getenv("CODE_INDEX_SERVICE_TOKEN", "").strip()
    github_token: str = os.getenv("CODE_INDEX_GITHUB_TOKEN", "").strip()
    max_files: int = int(os.getenv("CODE_INDEX_MAX_FILES", "400"))
    max_file_size_bytes: int = int(os.getenv("CODE_INDEX_MAX_FILE_SIZE_BYTES", str(500 * 1024)))
    max_symbols_per_file: int = int(os.getenv("CODE_INDEX_MAX_SYMBOLS_PER_FILE", "200"))
    index_timeout_seconds: int = int(os.getenv("CODE_INDEX_INDEX_TIMEOUT_SECONDS", "30"))
    poller_enabled: bool = os.getenv("CODE_INDEX_POLLER_ENABLED", "").strip().lower() in ("1", "true")
    poller_config: str = os.getenv("CODE_INDEX_POLLER_CONFIG", "./config/poll.json").strip()


settings = Settings()
