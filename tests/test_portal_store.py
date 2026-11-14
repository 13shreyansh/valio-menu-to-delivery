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


@pytest.fixture(scope="module")
def live_client():
    from fastapi.testclient import TestClient
    from api.index import app
    with TestClient(app,base_url="https://testserver") as client:
        yield client


def test_mcp_manager_is_running_with_application_lifespan(live_client):
    from fastapi.testclient import TestClient
    from api.index import app

    c=live_client
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


def test_kitchen_storage_isolated_and_legacy_preserved(monkeypatch,tmp_path):
    from chefagent.account_scope import kitchen_scope
    monkeypatch.delenv('BLOB_READ_WRITE_TOKEN',raising=False)
    monkeypatch.setenv('AURORA_LOCAL_DB',str(tmp_path/'scope.db'))
    Store(namespace='aurora').put('ledger',{'orders':['old test order']})
    Store().put('ledger',{'orders':['real chef order']})
    with kitchen_scope('test-'+'a'*32):
        assert Store().get('ledger')[0] is None
        Store().put('ledger',{'orders':['isolated test order']})
    assert Store().get('ledger')[0]['orders']==['real chef order']
    assert Store(namespace='aurora').get('ledger')[0]['orders']==['old test order']


def test_test_kitchen_cookie_and_ask_thread_keep_scope(monkeypatch,tmp_path,live_client):
    from fastapi.testclient import TestClient
    from api.index import app
    from chefagent import portal as p
    from chefagent.account_scope import account_id
    monkeypatch.delenv('BLOB_READ_WRITE_TOKEN',raising=False)
    monkeypatch.setenv('AURORA_LOCAL_DB',str(tmp_path/'webscope.db'))
    monkeypatch.setattr(p,'account',lambda:{'account_id':account_id()})
    monkeypatch.setattr(p,'apply_request',lambda *a,**kw:{'account_id':account_id()})
    c=live_client
    assert c.post('/api/login',headers={'x-valio-test-run':'a'*32}).status_code==200
    assert c.get('/api/account').json()['account_id']=='test-'+'a'*32
    assert 'test-'+'a'*32 in c.post('/api/ask',json={'draft_id':'b'*32,'text':'breakfast'}).text
    assert c.get('/api/account',headers={'x-valio-test-run':'b'*32}).status_code==422
    assert c.post('/api/login',headers={'x-valio-test-run':'../../aurora'}).status_code==400


def test_mcp_tools_use_request_kitchen_not_global_account(monkeypatch,tmp_path,live_client):
    from fastapi.testclient import TestClient
    from api.index import app
    from chefagent import portal as p
    from chefagent.account_scope import account_id
    monkeypatch.delenv('BLOB_READ_WRITE_TOKEN',raising=False)
    monkeypatch.setenv('AURORA_LOCAL_DB',str(tmp_path/'mcpscope.db'))
    seen=[]
    def prepared(text):
        seen.append(account_id())
        return {'question':'Which breakfast?'}
    monkeypatch.setattr(p,'prepare_assistant',prepared)
    headers={'Accept':'application/json, text/event-stream','x-valio-test-run':'c'*32}
    c=live_client
    r=c.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'prepare_order','arguments':{'request':'breakfast'}}})
    assert r.status_code==200
    assert seen==['test-'+'c'*32]
    del headers['x-valio-test-run']
    c.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'prepare_order','arguments':{'request':'breakfast'}}})
    assert seen[-1]=='aurora'
