from pydantic import BaseModel
import os


class Settings(BaseModel):
    trust_mode: str = os.getenv("CODE_INDEX_TRUST_MODE", "strict").strip().lower()
    signer: str = os.getenv("CODE_INDEX_SIGNER", "voro-index-guard").strip()
    signing_key: str = os.getenv("CODE_INDEX_SIGNING_KEY", "").strip()
    artifact_root: str = os.getenv("ARTIFACT_ROOT", "./data/artifacts").strip()
    service_token: str = os.getenv("CODE_INDEX_SERVICE_TOKEN", "").strip()


settings = Settings()
