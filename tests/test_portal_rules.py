import copy
from types import SimpleNamespace
import pytest
from chefagent import portal as p, kitchen as k, kitchen_fixtures as old


@pytest.fixture
def account(monkeypatch, tmp_path):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("AURORA_LOCAL_DB", str(tmp_path / "account.sqlite"))

    def ctx(rule):
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
