import copy
from types import SimpleNamespace
import pytest
from chefagent import portal as p, kitchen as k, kitchen_fixtures as old


@pytest.fixture
def account(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("AURORA_LOCAL_DB", str(tmp_path / "account.sqlite"))

    def ctx(rule, state=None, pool=None, placed=None):
        attrs = {
            n: copy.deepcopy(getattr(old, n))
            for n in [
                "KITCHEN",
                "INGREDIENTS",
                "STOCK",
                "RECIPES",
                "BASE_SERVICES",
                "DELIVERIES",
            ]
        }
        for role, amount in (pool or {}).items():
            attrs["STOCK"][role] = attrs["STOCK"].get(role, 0) + amount
        if placed:
            attrs["BASE_SERVICES"] = attrs["BASE_SERVICES"] + copy.deepcopy(placed[0])
            attrs["RECIPES"].update(copy.deepcopy(placed[1]))
        attrs["KITCHEN"]["policy"] = {
            "free_from": rule["allergens"],
            "strict_may_contain": True,
        }
        return SimpleNamespace(**attrs)

    monkeypatch.setattr(p, "context", ctx)
    monkeypatch.setattr(p, "load", k.load)
    return p


def wedding(account):
    account.save_rules({"weekly_limit": 1})
    out = account.new_draft()
    return account.apply_request(
        out["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Wedding Saturday 120 guests salmon soup whitefish potatoes lemon tart",
            "covers": 120,
            "dishes": [
                {"recipe": "soup", "covers": 120},
                {"recipe": "whitefish", "covers": 120},
                {"recipe": "tart", "covers": 120},
            ],
        },
    )


def test_new_wedding_quantities_are_recipe_scaled(account):
    o = wedding(account)
    # Existing 21 kg salmon covers the original 140 guests; the soup needs another 18 kg.
    assert next(r for r in o["rows"] if r["role"] == "fish")["need"] == 18
    assert next(r for r in o["rows"] if r["role"] == "whitefish")["need"] == 18
    assert next(r for r in o["rows"] if r["id"] == "2026-11-20-cream")["need"] == 21.2


def test_current_rules_cannot_be_bypassed_by_mcp(account):
    o = wedding(account)
    state, ver = p.draft(o["draft_id"])
    state["source"] = "Aurora Group assistant"
    p.Store().put("drafts/" + state["id"], state, ver)
    with pytest.raises(k.KitchenError, match="review"):
        account.place(o["draft_id"], assistant=True)


def test_block_limit_cannot_be_approved(account):
    o = wedding(account)
    account.save_rules({"over_limit": "block"})
    with pytest.raises(k.KitchenError):
        account.change(o["draft_id"], "approve", "budget")
    with pytest.raises(k.KitchenError):
        account.place(o["draft_id"])


def test_rule_edit_invalidates_prior_approval(account):
    o = wedding(account)
    account.change(o["draft_id"], "approve", "budget")
    account.save_rules({"growth_limit": 199})
    o = account.get_draft(o["draft_id"])
    assert not next(c for c in o["checks"] if c["id"] == "budget")["approved"]


def test_keep_original_remains_blocked_after_reload(account):
    o = wedding(account)
    account.change(o["draft_id"], "keep-original")
    o = account.get_draft(o["draft_id"])
    assert not o["can_place"]
    assert any(c["id"] == "keep-original" for c in o["checks"])


def test_quantity_edit_reopens_pack_and_spend_checks(account):
    o = wedding(account)
    for check in o["checks"]:
        if check["can_approve"]:
            o = account.change(o["draft_id"], "approve", check["id"])
    cream = next(r for r in o["rows"] if r["id"] == "2026-11-20-cream")
    o = account.change(
        o["draft_id"], "quantity", {"id": cream["id"], "units": cream["units"] + 1}
    )
    assert {"pack", "budget"} <= {
        c["id"] for c in o["checks"] if c["reopened"] and not c["approved"]
    }


def test_new_allergen_rule_applies_to_catalogue_and_existing_orders(account):
    o = wedding(account)
    account.save_rules({"allergens": ["nuts", "peanuts", "milk"]})
    o = account.get_draft(o["draft_id"])
    assert not o["can_place"]
    assert not any("milk" in r["contains"] for r in o["rows"] if r["units"] > 0)


def test_outside_assistant_cannot_place_chefs_draft(account):
    o = account.new_draft()
    with pytest.raises(k.KitchenError, match="connected assistant"):
        account.place(o["draft_id"], assistant=True)


def test_closing_a_day_removes_only_that_days_services(account):
    o = account.new_draft()
    out = account.apply_request(
        o["draft_id"],
        parsed={
            "status": "readable",
            "action": "close",
            "event": "Closure",
            "date": "2026-11-19",
            "transcript": "We're closed on Thursday",
            "covers": 0,
            "dishes": [],
        },
    )
    assert not any(s["date"] == "2026-11-19" for s in out["services"])
    assert any(s["date"] == "2026-11-18" for s in out["services"])
    assert out["total"] <= o["total"]


def test_empty_order_is_not_a_placed_purchase(account):
    o = account.new_draft(services=[], source="Aurora Group assistant")
    assert not o["can_place"]
    with pytest.raises(k.KitchenError):
        account.place(o["draft_id"], assistant=True)


def test_second_event_keeps_existing_wedding(account):
    first = account.new_draft()
    a = account.apply_request(
        first["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Wedding 120 lemon tart Saturday",
            "covers": 120,
            "date": "2026-11-21",
            "event": "Wedding",
            "dishes": [{"recipe": "tart", "covers": 120}],
        },
    )
    b = account.apply_request(
        first["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Also breakfast 40 Wednesday conference",
            "covers": 40,
            "date": "2026-11-18",
            "event": "Conference",
            "dishes": [{"recipe": "breakfast", "covers": 40}],
        },
    )
    assert any(
        s["date"] == "2026-11-21" and s["recipe"] == "tart" and s["covers"] == 120
        for s in b["services"]
    )
    assert any(
        s.get("wedding")
        and s["date"] == "2026-11-18"
        and s["recipe"] == "breakfast"
        and s["covers"] == 40
        for s in b["services"]
    )
    edited = account.apply_request(
        first["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Wedding 100 lemon tart Saturday",
            "covers": 100,
            "date": "2026-11-21",
            "event": "Wedding",
            "dishes": [{"recipe": "tart", "covers": 100}],
        },
        replace_event_id=a["reading"]["event_id"],
    )
    assert sum(s["recipe"] == "tart" for s in edited["services"]) == 1
    assert next(s["covers"] for s in edited["services"] if s["recipe"] == "tart") == 100
    assert any(
        s.get("wedding") and s["date"] == "2026-11-18" for s in edited["services"]
    )


def test_committed_snapshot_survives_failed_draft_write_and_price_changes(
    account, monkeypatch, supplier
):
    import httpx

    o = account.new_draft(
        services=[{"date": "2026-11-18", "recipe": "breakfast", "covers": 40}],
        source="Aurora Group assistant",
    )
    original = account.Store.put

    def put(self, key, value, version=None):
        if key == "drafts/" + o["draft_id"] and value.get("status") == "placed":
            raise httpx.ReadTimeout("Injected failed convenience write")
        return original(self, key, value, version)

    monkeypatch.setattr(account.Store, "put", put)
    placed = account.place(o["draft_id"], assistant=True)
    assert account.draft(o["draft_id"])[0]["status"] == "draft"
    supplier.price_factor = 2
    retry = account.place(o["draft_id"], assistant=True)
    assert (
        retry["total"] == placed["total"]
        and retry["order_number"] == placed["order_number"]
    )
    assert account.get_draft(o["draft_id"])["total"] == placed["total"]
    assert len(account.ledger()[0]["orders"]) == 1
    with pytest.raises(k.KitchenError):
        account.change(o["draft_id"], "add", "463380")


def test_external_draft_is_indexed_for_chef_review(account):
    o = account.new_draft(
        services=[{"date": "2026-11-18", "recipe": "breakfast", "covers": 40}],
        source="Aurora Group assistant",
    )
    entries = account.ledger()[0]["drafts"]
    assert any(
        d["draft_id"] == o["draft_id"]
        and d["placed_by"] == "Aurora Group assistant"
        and d["status"] == "Draft"
        for d in entries
    )
    placed = account.place(o["draft_id"], assistant=True)
    book = account.ledger()[0]
    assert not any(d["draft_id"] == o["draft_id"] for d in book["drafts"])
    assert book["orders"][0]["order_number"] == placed["order_number"]


def test_mcp_rule_errors_tell_the_assistant_why_it_needs_a_chef(account):
    from chefagent.mcp_server import place_order
    from mcp.server.mcpserver.exceptions import ToolError

    account.save_rules({"weekly_limit": 0.1, "over_limit": "block"})
    o = account.new_draft(
        services=[{"date": "2026-11-18", "recipe": "breakfast", "covers": 40}],
        source="Aurora Group assistant",
    )
    with pytest.raises(ToolError, match="chef to review"):
        place_order(o["draft_id"])


def test_final_wedding_photo_replaces_wedding_even_when_its_event_name_differs(account):
    o = account.new_draft()
    account.apply_request(
        o["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Saturday wedding 120 salmon soup",
            "covers": 120,
            "date": "2026-11-21",
            "event": "Saturday wedding",
            "dishes": [{"recipe": "soup", "covers": 120}],
        },
    )
    out = account.apply_request(
        o["draft_id"],
        source="photo",
        parsed={
            "status": "readable",
            "transcript": "Final wedding whitefish120 tart120 cheeseboard140 No soup",
            "covers": 120,
            "date": "2026-11-21",
            "event": "Wedding",
            "dishes": [
                {"recipe": "whitefish", "covers": 120},
                {"recipe": "tart", "covers": 120},
                {"recipe": "cheeseboard", "covers": 140},
            ],
        },
    )
    events = [s for s in out["services"] if s.get("wedding")]
    assert [s["recipe"] for s in events] == ["whitefish", "tart", "cheeseboard"]
    assert next(s["covers"] for s in events if s["recipe"] == "cheeseboard") == 140


def test_a_conference_photo_does_not_replace_a_wedding_on_the_same_day(account):
    o = account.new_draft()
    account.apply_request(
        o["draft_id"],
        parsed={
            "status": "readable",
            "transcript": "Wedding120 tart Saturday",
            "covers": 120,
            "date": "2026-11-21",
            "event": "Wedding",
            "dishes": [{"recipe": "tart", "covers": 120}],
        },
    )
    out = account.apply_request(
        o["draft_id"],
        source="photo",
        parsed={
            "status": "readable",
            "transcript": "Saturday conference breakfast40",
            "covers": 40,
            "date": "2026-11-21",
            "event": "Conference",
            "dishes": [{"recipe": "breakfast", "covers": 40}],
        },
    )
    events = [s for s in out["services"] if s.get("wedding")]
    assert any(s["recipe"] == "tart" and s["covers"] == 120 for s in events)
    assert any(s["recipe"] == "breakfast" and s["covers"] == 40 for s in events)


def test_new_external_service_draft_returns_growth_check_immediately(account):
    account.save_rules({"growth_limit":1})
    o=account.new_draft(services=copy.deepcopy(old.BASE_SERVICES))
    assert any(c['id']=='growth' for c in o['checks'])
    assert not o['can_place']
    for c in o['checks']:
        if c['can_approve']:o=account.change(o['draft_id'],'approve',c['id'])
    assert account.place(o['draft_id'])['status']=='placed'


def test_reconstructed_past_delivery_keeps_flow_totals_and_supplier_evidence(account):
    from scripts.repair_aurora import delivered_copy
    o=account.new_draft()
    for c in o['checks']:
        if c['can_approve']:o=account.change(o['draft_id'],'approve',c['id'])
    placed=account.place(o['draft_id'])
    past=delivered_copy(placed,'2026-11-02')
    assert past['total']==placed['total']==round(sum(r['total'] for r in past['rows']),2)
    assert [d['date'] for d in past['deliveries']]==['2026-11-02','2026-11-04','2026-11-06']
    assert past['placed_at'].startswith('2026-11-01')
    assert past['evidence']==placed['evidence']
    assert set(r['delivery'] for r in past['rows'])=={'2026-11-02','2026-11-04','2026-11-06'}


def test_concurrent_placement_rechecks_cumulative_budget(account, monkeypatch):
    o = account.new_draft()
    account.save_rules({"weekly_limit": round(o["total"] * 1.5, 2), "monthly_limit": 100000, "over_limit": "block"})
    o = account.get_draft(o["draft_id"])
    for check in o["checks"]:
        if check["can_approve"]:
            o = account.change(o["draft_id"], "approve", check["id"])
    assert o["can_place"]
    original_put = p.Store.put
    injected = False
    def racing_put(store, key, value, version=None):
        nonlocal injected
        if key == "ledger" and not injected and any(x["draft_id"] == o["draft_id"] for x in value["orders"]):
            injected = True
            competing, current = store.get("ledger")
            competing["orders"].append({"draft_id": "b" * 32, "order_number": "OTHER", "total": o["total"],
                                         "week": 47, "status": "Placed", "placed_at": "2026-11-15T08:00:00+02:00"})
            original_put(store, "ledger", competing, current)
        return original_put(store, key, value, version)
    monkeypatch.setattr(p.Store, "put", racing_put)
    with pytest.raises(k.KitchenError, match="another order"):
        account.place(o["draft_id"])
    assert [x["draft_id"] for x in account.ledger()[0]["orders"]] == ["b" * 32]
