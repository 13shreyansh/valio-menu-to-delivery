"""Regressions for the judge's review of 15 Nov: limits, honest log, repeat orders, tokens."""
import pytest
from chefagent import portal as p, kitchen as k
from tests.test_portal_rules import account  # noqa: F401  (isolated kitchen fixture)


def approve_all(account, o):
    for c in o["checks"]:
        if c["can_approve"] and not c["approved"]:
            o = account.change(o["draft_id"], "approve", c["id"])
    return o


def milk_line(account, units, source="Sanna Virtanen", increment=False):
    o = account.new_draft(source=source, increment=increment)
    state, version = p.draft(o["draft_id"])
    state["extra"].append({"product_id": "463380", "units": units, "delivery": "2026-11-16"})
    p.Store().put("drafts/" + state["id"], state, version)
    return account.get_draft(o["draft_id"])


def test_weekly_limit_counts_orders_already_placed_in_every_channel(account):
    # Review: with EUR 5,262 placed, an MCP order of EUR 88.98 went through "Within your rules".
    account.save_rules({"weekly_limit": 100000, "growth_limit": 100000})
    first = account.place(approve_all(account, account.new_draft())["draft_id"])
    account.save_rules({"weekly_limit": first["total"] + 5})
    o = milk_line(account, 10, source="Aurora Group assistant", increment=True)
    budget = next(c for c in o["checks"] if c["id"] == "budget")
    assert o["week_placed"] == first["total"] and not o["can_place"]
    assert "already placed" in budget["text"]
    with pytest.raises(k.KitchenError, match="person to approve"):
        account.place(o["draft_id"], assistant=True)
    assert any("needs your OK" in e["text"] for e in account.ledger()[0]["events"])


def test_monthly_limit_is_enforced(account):
    account.save_rules({"weekly_limit": 100000, "growth_limit": 100000, "monthly_limit": 1})
    o = account.new_draft()
    assert any(c["id"] == "monthly" for c in o["checks"]) and not o["can_place"]


def test_same_week_is_not_ordered_twice(account):
    account.save_rules({"weekly_limit": 100000, "growth_limit": 100000})
    first = account.place(approve_all(account, account.new_draft())["draft_id"])
    again = account.new_draft()
    assert first["total"] > 0 and again["total"] == 0
    assert not again["can_place"]


def test_repeated_product_order_is_flagged(account):
    account.save_rules({"weekly_limit": 100000, "growth_limit": 100000})
    account.place(approve_all(account, account.new_draft())["draft_id"])
    account.place(approve_all(account, milk_line(account, 3))["draft_id"])
    o = milk_line(account, 3)
    assert any(c["kind"] == "duplicate" for c in o["checks"])


def test_log_says_who_approved_and_never_claims_within_rules(account):
    # Review: the bell said "Within your rules" for an order EUR 1,330 over the limit.
    account.save_rules({"weekly_limit": 1})
    o = approve_all(account, account.new_draft())
    placed = account.place(o["draft_id"])
    events = account.ledger()[0]["events"]
    assert placed["within_rules"] is False and "approval" in placed["rule_note"]
    assert "Within your rules" not in events[0]["note"]
    assert any(e["text"].startswith("Sanna approved") for e in events)
    assert any(e["text"].startswith("Sanna changed weekly limit") for e in events)


def test_edit_after_approval_reopens_it(account):
    account.save_rules({"weekly_limit": 1})
    o = approve_all(account, account.new_draft())
    assert o["can_place"]
    row = next(r for r in o["rows"] if r["units"] > 0)
    o = account.change(o["draft_id"], "quantity", {"id": row["id"], "units": row["units"] + 1})
    assert not o["can_place"] and any(c["reopened"] for c in o["checks"])


def test_change_response_is_small(account):
    import json
    o = account.new_draft()
    assert "evidence" not in p.slim(o) and len(json.dumps(p.slim(o))) < 200_000


def test_token_names_its_account_and_must_match(account):
    token = account.mcp_token()
    assert p.token_account(token) == "aurora" and p.token_valid(token)
    assert p.token_account("anything") is None
    assert not p.token_valid(token[:-2] + "zz")
    new = account.mcp_token(regenerate=True)
    assert new != token and not p.token_valid(token) and p.token_valid(new)
