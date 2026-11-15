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


def token_for(account, monkeypatch, tmp_path):
    from chefagent import portal as p
    from chefagent.account_scope import kitchen_scope
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("AURORA_LOCAL_DB", str(tmp_path / "tokens.db"))
    with kitchen_scope(account):
        return p.mcp_token()


@pytest.fixture(scope="module")
def live_client():
    from fastapi.testclient import TestClient
    from api.index import app
    with TestClient(app,base_url="https://testserver") as client:
        yield client


def test_mcp_manager_is_running_with_application_lifespan(live_client, monkeypatch, tmp_path):
    c=live_client
    token = token_for("aurora", monkeypatch, tmp_path)
    # Regression: the door was open to anyone. No token or a wrong token is refused.
    assert c.post("/mcp/", headers={"Accept": "application/json, text/event-stream"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    assert c.post("/mcp/", headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer " + token[:-3] + "abc"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 401
    r = c.post(
        "/mcp/",
        headers={"Accept": "application/json, text/event-stream", "Authorization": "Bearer " + token},
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
    def prepared(text, parsed=None):
        seen.append(account_id())
        return {'question':'Which breakfast?'}
    monkeypatch.setattr(p,'assistant_request',prepared)
    test_token=token_for('test-'+'c'*32,monkeypatch,tmp_path)
    aurora_token=token_for('aurora',monkeypatch,tmp_path)
    headers={'Accept':'application/json, text/event-stream','Authorization':'Bearer '+test_token}
    c=live_client
    r=c.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'prepare_order','arguments':{'request':'breakfast'}}})
    assert r.status_code==200
    assert seen==['test-'+'c'*32]
    headers['Authorization']='Bearer '+aurora_token
    c.post('/mcp/',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'prepare_order','arguments':{'request':'breakfast'}}})
    assert seen[-1]=='aurora'
