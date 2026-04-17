from fastapi import Header, HTTPException

from voro_mcp.config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Simple bearer token guard for service-to-service callers."""
    token = settings.service_token
    if not token:
        # Dev mode: token guard disabled when CODE_INDEX_SERVICE_TOKEN is unset.
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"reason_code": "unauthorized", "message": "missing bearer token"})

    presented = authorization.split(" ", 1)[1].strip()
    if presented != token:
        raise HTTPException(status_code=401, detail={"reason_code": "unauthorized", "message": "invalid bearer token"})
