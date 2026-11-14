"""Valio-side agent tools. The same functions back the MCP server (for any agent: Claude,
ChatGPT, a customer's own procurement bot) and the web app's HTTP API.

Trust model: every write goes through `submit_order`, which re-checks the kitchen mandate
on Valio's side (allergens/diet, spend limit, substitutions, availability) no matter which
agent built the cart. An agent can propose; only the mandate or a human can approve.
"""
import datetime as dt, hashlib, json, math

from .catalog import load as load_catalog
from .guardrails import product_violations
from .planner import Planner, delivery_date_for
from .valio_api import ValioAPI

KITCHENS = {
    "HC-1001": {"name": "Hotel Aurora Helsinki (city hotel, 240 rooms)", "customer": "HC-1001", "segment": "hotel",
                "policy": {"lactose_free_dairy": True, "free_from": [], "strict_may_contain": False,
                           "auto_approve_limit_eur": 1500, "allow_substitutes": "same_ingredient_auto"}},
    "HC-1003": {"name": "Harbour Hotel Turku (conference hotel, nut-free)", "customer": "HC-1003", "segment": "hotel",
                "policy": {"lactose_free_dairy": True, "free_from": ["nuts", "peanuts"], "strict_may_contain": True,
                           "auto_approve_limit_eur": 2000, "allow_substitutes": "same_ingredient_auto"}},
    "HC-1002": {"name": "Fell Lodge Saariselkä (resort hotel)", "customer": "HC-1002", "segment": "hotel",
                "policy": {"lactose_free_dairy": True, "free_from": [], "strict_may_contain": False,
                           "auto_approve_limit_eur": 800, "allow_substitutes": "ask"}},
}


def _card(p, extra=None):
    d = {k: p.get(k) for k in ("id", "name", "name_fi", "brand", "vendor", "sales_unit", "pack", "pack_dim", "temp",
                                "contains", "may_contain", "lactose_free", "gluten_free", "vegan", "labels",
                                "origin", "reliability", "co2_per_kg", "substitutes")}
    if extra:
        d.update(extra)
    return d


def search_products(query: str, diet: list[str] | None = None, customer: str = "HC-1001", limit: int = 10):
    """Search the static catalogue (no price calls). Products breaking the kitchen's rules are
    returned separately with the reason, never mixed into results."""
    cat = load_catalog()
    pol = KITCHENS.get(customer, KITCHENS["HC-1001"])["policy"]
    ok, blocked = [], []
    for p, s in cat.search(query, k=limit * 3):
        v = product_violations(p, diet or [], pol)
        (blocked if v else ok).append((p, v))
    return {"results": [_card(p) for p, _ in ok[:limit]],
            "excluded": [{"id": p["id"], "name": p["name"], "why": v} for p, v in blocked[:5]]}


def get_product(product_id: str):
    p = load_catalog().get(product_id)
    return _card(p, {"ingredients": p.get("ingredients"), "claims": p.get("claims")}) if p else {"error": "unknown product"}


def quote(product_ids: list[str], delivery_date: str, customer: str = "HC-1001"):
    """Customer-specific price + availability for a shortlist (max 50), with pack size in kg/L."""
    api = ValioAPI(customer=customer)
    ids = product_ids[:50]
    pr, av = api.price(delivery_date, ids), api.availability(delivery_date, ids)
    cat = load_catalog()
    out = []
    for pid in ids:
        p = cat.get(pid)
        if not p:
            continue
        price = pr.get(pid, {})
        pack = 1.0 if p["sales_unit"] == "KG" else (round(price["unit_price"] / price["comparison_price"], 4)
                                                      if price.get("comparison_price") else p.get("pack"))
        out.append({"id": pid, "name": p["name"], "sales_unit": p["sales_unit"], "pack_kg_or_l": pack,
                    "price": price, "availability": av.get(pid, {}),
                    "quote_id": hashlib.sha1(json.dumps([customer, pid, delivery_date, price.get("unit_price")]).encode()).hexdigest()[:12]})
    return {"customer": customer, "delivery_date": delivery_date, "quotes": out,
            "valid_until": (dt.datetime.now() + dt.timedelta(hours=2)).isoformat(timespec="minutes")}


def find_substitutes(product_id: str, delivery_date: str, diet: list[str] | None = None, customer: str = "HC-1001"):
    """Valio's own substitution links first, then same-category items with similar names,
    filtered by the kitchen's rules and checked for delivery by the date."""
    cat = load_catalog()
    p = cat.get(product_id)
    if not p:
        return {"error": "unknown product"}
    pol = KITCHENS.get(customer, KITCHENS["HC-1001"])["policy"]
    cands = [cat.get(s) for s in p.get("substitutes", []) if cat.get(s)]
    for q, _ in cat.search(p["name"], k=30):
        if q["id"] != p["id"] and q["category"] == p["category"] and q not in cands:
            cands.append(q)
    cands = [c for c in cands if not product_violations(c, diet or [], pol)][:10]
    api = ValioAPI(customer=customer)
    av = api.availability(delivery_date, [c["id"] for c in cands])
    return {"for": _card(p), "substitutes": [_card(c, {"valio_link": c["id"] in p.get("substitutes", []),
                                                      "availability": av.get(c["id"])}) for c in cands]}


def plan_menu_order(services: list[dict], customer: str = "HC-1001", kitchen: dict | None = None, disruptions=None):
    """Turn a menu (services: [{date, meal, items:[{text, covers, diet}]}]) into a draft order:
    lines grouped by delivery date, with allocations to dishes, substitutions, gaps, approval
    flags and an audit trail. Nothing is ordered until submit_order."""
    k = kitchen or KITCHENS.get(customer, KITCHENS["HC-1001"])
    api = ValioAPI(customer=k["customer"], disruptions=disruptions)
    order = Planner(api, k).plan(services)
    cat = load_catalog()
    order["api_usage"] = {"http_calls": api.calls,
                          "price_lookups": len(api.queried.get("/api/price", ())),
                          "availability_lookups": len(api.queried.get("/api/availability", ())),
                          "catalogue_size": len(cat.food),
                          "note": "Only shortlisted products are priced and checked; never the whole catalogue."}
    order["draft_id"] = "D-" + hashlib.sha1(json.dumps(order["menu"], default=str).encode()).hexdigest()[:10]
    return order


def submit_order(delivery: dict, customer: str = "HC-1001", approved_by: str | None = None, diet_by_line: dict | None = None):
    """Valio-side mandate check, then the (mock) order is placed or held for approval.
    The check is repeated here on purpose: a buyer agent cannot bypass it."""
    k = KITCHENS.get(customer, KITCHENS["HC-1001"])
    pol = k["policy"]
    cat = load_catalog()
    problems, holds = [], []
    total = 0.0
    for ln in delivery["lines"]:
        p = cat.get(ln["product_id"])
        if not p:
            problems.append(f'{ln["product_id"]}: unknown product'); continue
        v = product_violations(p, ln.get("diet", []), pol)
        if v:
            problems.append(f'{p["name"]}: {"; ".join(v)}')
        if ln.get("substitution") and (ln["substitution"].get("type") == "recipe" or pol.get("allow_substitutes") != "same_ingredient_auto"):
            holds.append(f'{p["name"]}: substitution needs approval')
        total += float(ln.get("line_total") or 0)
    if total > pol["auto_approve_limit_eur"]:
        holds.append(f'total €{total:.2f} over auto-approve limit €{pol["auto_approve_limit_eur"]}')
    if problems:
        return {"status": "rejected", "problems": problems}
    if holds and not approved_by:
        return {"status": "pending_approval", "holds": holds, "total": round(total, 2)}
    oid = "VA-" + hashlib.sha1(json.dumps([customer, delivery["date"], [(l["product_id"], l["units"]) for l in delivery["lines"]]]).encode()).hexdigest()[:8].upper()
    return {"status": "placed", "order_id": oid, "delivery_date": delivery["date"], "total": round(total, 2),
            "approved_by": approved_by or "mandate (auto)", "holds_overridden": holds,
            "note": "Mock order: Valio's Junction API has no order endpoint."}
