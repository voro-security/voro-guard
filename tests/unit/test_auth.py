import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from voro_mcp.config import settings
from voro_mcp.security import require_auth


def setup_function() -> None:
    settings.service_token = ""


def test_auth_disabled_when_no_service_token() -> None:
    require_auth(None)


def test_missing_bearer_token_rejected() -> None:
    settings.service_token = "secret"
    try:
        require_auth(None)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["reason_code"] == "unauthorized"


def test_invalid_bearer_token_rejected() -> None:
    settings.service_token = "secret"
    try:
        require_auth("Bearer wrong")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["reason_code"] == "unauthorized"


def test_valid_bearer_token_allowed() -> None:
    settings.service_token = "secret"
    require_auth("Bearer secret")
