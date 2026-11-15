"""Make Hotel Aurora clean for recording. Nothing is deleted: week 47 orders,
drafts and the activity log move to an archive list inside the ledger.

Past weeks are built through the same order engine (new draft, approve, place)
and then dated as delivered kitchen history, valued at today's real Valio prices.
"""
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chefagent import portal as p
from chefagent.account_store import Store, save_seed
from chefagent.account_scope import kitchen_scope
from scripts.repair_aurora import delivered_copy


def build_history():
    made = []
    for week_start, factor in [("2026-10-26", 0.84), ("2026-11-02", 0.94), ("2026-11-09", 1.04)]:
        services = copy.deepcopy(p.f.BASE_SERVICES)
        for s in services:
            s["covers"] = round(s["covers"] * factor)
        o = p.new_draft(services=services)
        for c in o["checks"]:
            if not c["approved"]:
                if not c["can_approve"]:
                    raise RuntimeError("A past week cannot pass the current rules: " + c["text"])
                o = p.change(o["draft_id"], "approve", c["id"])
        placed = p.place(o["draft_id"])
        past = delivered_copy(placed, week_start)
        key = "completed-history/" + placed["draft_id"]
        Store().put(key, past)

        def date_it(book):
            e = next(e for e in book["orders"] if e["draft_id"] == placed["draft_id"])
            e.update(snapshot_key=key, placed_at=past["placed_at"], status="Delivered", week=past["week"], historical=True,
                     price_checked_at=past["price_checked_at"], rows=past["rows"], deliveries=past["deliveries"], rule_note="", within_rules=None, bought={})
        p.update_ledger(date_it)
        made.append({"order": placed["order_number"], "week": past["week"], "total": placed["total"]})
    return made


def reset():
    rules, version = Store().get("rules")
    fresh = {**copy.deepcopy(p.f.RULES), "changed_at": "2026-11-02", "changed_by": "Sanna", "version": (rules or {}).get("version", 0) + 1}
    Store().put("rules", fresh, version)
    book, _ = p.ledger()
    made = build_history() if not any(o.get("historical") for o in book["orders"]) else []

    def clean(book):
        keep = [o for o in book["orders"] if o.get("historical")]
        book.setdefault("archive", []).append({"at": p.now(), "orders": [o for o in book["orders"] if not o.get("historical")], "drafts": book.get("drafts", []), "events": book["events"]})
        book["orders"], book["drafts"], book["events"] = keep, [], []
        return {"history": [(o["order_number"], o["total"]) for o in keep], "archived_orders": len(book["archive"][-1]["orders"]), "archived_drafts": len(book["archive"][-1]["drafts"])}
    out = p.update_ledger(clean)
    p.new_draft()  # next week's order is prepared and waiting
    seeded = save_seed()  # every "Try the demo account" visit starts from this clean copy
    return {**out, "seeded_private_copies": seeded, "built": made, "rules": {k: fresh[k] for k in ["weekly_limit", "monthly_limit", "growth_limit", "over_limit", "allergens"]}, "token_ready": bool(p.mcp_token())}


if __name__ == "__main__":
    with kitchen_scope("aurora"):
        print(json.dumps(reset(), indent=2))
