import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voro_mcp.core.indexer import build_payload_from_repo


class _Resp:
    def __init__(self, json_data=None, text_data="", status_code=200):
        self._json_data = json_data or {}
        self.text = text_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_github_owner_repo_ref_indexing(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if "/git/trees/HEAD" in url:
            return _Resp(
                {
                    "tree": [
                        {"type": "blob", "path": "src/main.py", "size": 120},
                        {"type": "blob", "path": "README.md", "size": 50},
                    ]
                }
            )
        if "/contents/src/main.py" in url:
            return _Resp(text_data="def scan_contract(x):\n    return x\n")
        return _Resp(status_code=404)

    monkeypatch.setattr("voro_mcp.core.indexer.httpx.get", fake_get)
    payload = build_payload_from_repo("owner/repo")
    assert payload["repo_ref"] == "owner/repo"
    assert payload["stats"]["file_count"] == 1
    assert any(s["name"] == "scan_contract" for s in payload["symbols"])


def test_github_url_ref_indexing(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if "/git/trees/HEAD" in url:
            return _Resp({"tree": [{"type": "blob", "path": "lib/app.ts", "size": 200}]})
        if "/contents/lib/app.ts" in url:
            return _Resp(text_data="export function runAudit() { return true }\n")
        return _Resp(status_code=404)

    monkeypatch.setattr("voro_mcp.core.indexer.httpx.get", fake_get)
    payload = build_payload_from_repo("https://github.com/acme/scan-repo")
    assert payload["repo_ref"] == "acme/scan-repo"
    assert payload["stats"]["file_count"] == 1
    assert payload["stats"]["symbol_count"] >= 1
