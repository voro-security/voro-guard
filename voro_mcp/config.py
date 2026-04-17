from pydantic import BaseModel
import os


class Settings(BaseModel):
    trust_mode: str = os.getenv("CODE_INDEX_TRUST_MODE", "strict").strip().lower()
    signer: str = os.getenv("CODE_INDEX_SIGNER", "voro-index-guard").strip()
    signing_key: str = os.getenv("CODE_INDEX_SIGNING_KEY", "").strip()
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
