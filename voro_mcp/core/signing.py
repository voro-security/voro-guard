import hashlib
import hmac
import json
from typing import Any


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sign_hash(hash_hex: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), hash_hex.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(hash_hex: str, sig: str, secret: str) -> bool:
    expected = sign_hash(hash_hex, secret)
    return hmac.compare_digest(expected, sig)
