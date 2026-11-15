"""Regression: Valio's API answering 429 on every retry used to crash on r.json() of the
error body and surface as the generic 'Valio is unavailable' banner (Sun 15 Nov 05:40)."""
import time
import httpx, pytest
from chefagent import valio_api as v


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._body, self.headers = code, body, {}
    def json(self):
        if self._body is None: raise ValueError("no json")
        return self._body
    def raise_for_status(self):
        if self.status_code >= 400: raise httpx.HTTPStatusError("x", request=None, response=None)


@pytest.fixture(autouse=True)
def fast(monkeypatch, tmp_path):
    monkeypatch.setattr(v.time, "sleep", lambda s: None)
    monkeypatch.setattr(v, "CACHE", tmp_path / "c.json")
    v._mem.clear(); v._mem_path[0] = v.CACHE


def test_429_every_time_raises_specific_busy_error(monkeypatch):
    monkeypatch.setattr(v.httpx, "post", lambda *a, **k: Resp(429))
    with pytest.raises(v.ValioBusy) as e:
        v.ValioAPI(fresh=True).price("2026-11-16", ["469477"])
    assert "busy" in str(e.value) and "nothing was changed" in str(e.value)


def test_429_then_ok_succeeds(monkeypatch):
    calls = iter([Resp(429), Resp(429), Resp(200, {"products": [{"productId": "469477", "catalogPrice": {"value": 0.88}}]})])
    monkeypatch.setattr(v.httpx, "post", lambda *a, **k: next(calls))
    assert v.ValioAPI(fresh=True).price("2026-11-16", ["469477"])["469477"]["unit_price"] == 0.88


def test_busy_reuses_recent_answer_and_logs_it(monkeypatch):
    v._mem["HC-1001|/api/price|2026-11-16|469477"] = {"at": time.time() - 300, "row": {"productId": "469477", "catalogPrice": {"value": 0.88}}}
    monkeypatch.setattr(v.httpx, "post", lambda *a, **k: Resp(429))
    api = v.ValioAPI(fresh=True)
    assert api.price("2026-11-16", ["469477"])["469477"]["unit_price"] == 0.88
    assert any("Valio was busy" in a.get("source", "") for a in api.audit)


def test_non_json_200_is_retried_not_crashed(monkeypatch):
    calls = iter([Resp(200, None), Resp(200, {"products": []})])
    monkeypatch.setattr(v.httpx, "post", lambda *a, **k: next(calls))
    assert v.ValioAPI(fresh=True).price("2026-11-16", ["1"]) == {}


def test_plain_milk_detection():
    from chefagent.portal_intake import plain_milk, milk_kind
    assert plain_milk({"name": "milk"})
    assert not plain_milk({"name": "lactose-free milk", "lactose_free": True})
    assert not plain_milk({"name": "skimmed milk"})
    assert not plain_milk({"name": "oat milk"})
    assert milk_kind("Valio kevytmaito 1 l") == "semi-skimmed milk"
