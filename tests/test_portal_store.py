import pytest
from chefagent.account_store import Store, Conflict


def test_conditional_update_prevents_lost_orders(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("AURORA_LOCAL_DB", str(tmp_path / "account.db"))
    s = Store()
    v = s.put("ledger", {"orders": []})
    s.put("ledger", {"orders": [1]}, v)
    with pytest.raises(Conflict):
        s.put("ledger", {"orders": [2]}, v)
    assert s.get("ledger")[0]["orders"] == [1]


def test_private_blob_read_uses_exact_returned_path(monkeypatch):
    # Regression: an arbitrary cache-buster query made private Blob return 404.
    from chefagent import account_store as a

    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_storeid_test")
    seen = []

    class R:
        status_code = 200
        headers = {"etag": "v1"}

        def json(self):
            return {"orders": []}

        def raise_for_status(self):
            pass

    def get(url, **kw):
        seen.append((url, kw))
        return R()

    monkeypatch.setattr(a.httpx, "get", get)
    assert Store().get("ledger")[0] == {"orders": []}
    assert seen[0][1]["headers"]["Accept-Encoding"] == "identity"
    assert "?" not in seen[0][0] and seen[0][1]["params"] == {"cache": "0"}


def test_mcp_manager_is_running_with_application_lifespan():
    from fastapi.testclient import TestClient
    from api.index import app

    with TestClient(app) as c:
        r = c.post(
            "/mcp/",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "regression", "version": "1"},
                },
            },
        )
        assert r.status_code == 200 and "serverInfo" in r.json()["result"]
