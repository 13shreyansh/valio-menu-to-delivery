"""One ordering engine and account ledger for the portal and remote MCP clients."""

import httpx

import base64, copy, datetime as dt, hashlib, hmac, math, re, secrets, time, uuid
from types import SimpleNamespace
from . import kitchen as k, portal_fixtures as f
from .account_store import Store, Conflict
from .kitchen_intake import understand
from .guardrails import product_violations
from .valio_api import ValioAPI
from .catalog import load
from .account_scope import account_id, account_name
from .portal_intake import ALLERGENS, ROLE_LABELS, nice_day

now = lambda: dt.datetime.now(k.TZ).isoformat()
import os

SITE = os.environ.get("PUBLIC_URL", "https://valio-menu-to-delivery.vercel.app").rstrip("/")
eur = lambda v: f"€{v:,.2f}"
ALLERGEN_WORDS = {"milk": "dairy", "gluten": "gluten", "egg": "egg", "nuts": "nuts", "lactose": "lactose"}


def rules():
    value, version = Store().get("rules")
    value = value or copy.deepcopy(f.RULES)
    value.setdefault("monthly_limit", f.RULES["monthly_limit"])
    return value, version


def update_ledger(fn):
    """Apply fn(book) with optimistic retries. Returns fn's result."""
    for attempt in range(5):
        book, etag = ledger()
        result = fn(book)
        try:
            Store().put("ledger", book, etag)
            return result
        except Conflict:
            if attempt == 4:
                raise


def event(text, note="", by="Sanna Virtanen", total=None, link=None):
    return {"id": uuid.uuid4().hex[:12], "by": by, "text": text, "note": note, "total": total, "at": now(), "link": link}


def log_event(*args, **kwargs):
    item = event(*args, **kwargs)
    update_ledger(lambda book: book["events"].insert(0, item))
    return item


RULE_NAMES = {
    "weekly_limit": "weekly limit", "monthly_limit": "monthly limit", "growth_limit": "bigger-change limit",
    "over_limit": "over-limit rule", "ask_swap": "ask before swaps", "same_allergens": "same-allergen swaps",
    "allergens": "kitchen allergens",
}


def save_rules(value):
    current, etag = rules()
    before = copy.deepcopy(current)
    for key in ["weekly_limit", "growth_limit", "monthly_limit"]:
        n = value.get(key, current[key])
        if (
            isinstance(n, bool)
            or not isinstance(n, (float, int))
            or not math.isfinite(n)
            or not 0 < n <= 1000000
        ):
            raise k.KitchenError("Enter a limit above zero.")
        current[key] = round(n, 2)
    if value.get("over_limit", current["over_limit"]) not in ("ask", "block"):
        raise k.KitchenError("Choose what happens over the weekly limit.")
    current["over_limit"] = value.get("over_limit", current["over_limit"])
    for key in ["ask_swap", "same_allergens"]:
        if key in value:
            if type(value[key]) is not bool:
                raise k.KitchenError("Use an on or off setting.")
            current[key] = value[key]
    if "allergens" in value:
        if not isinstance(value["allergens"], list) or any(
            a not in ALLERGENS for a in value["allergens"]
        ):
            raise k.KitchenError("Choose an allergen from the list.")
        current["allergens"] = list(dict.fromkeys(value["allergens"]))
    changes = []
    for key in RULE_NAMES:
        if before.get(key) != current.get(key):
            show = lambda v: eur(v) if key.endswith("limit") and key != "over_limit" else ("on" if v is True else "off" if v is False else ", ".join(v) or "none" if isinstance(v, list) else {"ask": "ask me first", "block": "don't allow"}.get(v, str(v)))
            changes.append(f"{RULE_NAMES[key]} from {show(before.get(key))} to {show(current.get(key))}")
    if not changes:
        return current
    current.update(changed_at=now(), changed_by="Sanna", version=current["version"] + 1)
    Store().put("rules", current, etag)
    log_event("Sanna changed " + "; ".join(changes), note="Ordering rule change")
    return current


def week_orders(book, skip=None):
    return [o for o in book["orders"] if o.get("week") == 47 and o.get("status") == "Placed" and o["draft_id"] != skip]


def spend(book, skip=None):
    week = round(sum(o["total"] for o in week_orders(book, skip)), 2)
    month = round(sum(o["total"] for o in book["orders"] if o["placed_at"].startswith("2026-11") and o["draft_id"] != skip), 2)
    return week, month


HUGE = {"l": 5000, "kg": 2000, "pcs": 5000}  # one request line above this needs a person to check the amount


def placed_key(draft_id, recipe, state):
    """Assumed recipes get a per-order key so two orders' "beef stew" never collide."""
    return recipe if recipe not in (state.get("custom_recipes") or {}) else draft_id[:8] + "-" + recipe


def placed_events(others):
    """Events (weddings, lunches...) on already placed orders. Their purchases are in the stock pool,
    so their demand must be too, or a new event would eat the stock bought for an old one."""
    services, recipes, ingredients = [], {}, {}
    for o in others:
        for sv in o.get("event_services") or []:
            services.append({**sv, "wedding": False, "placed_event": True})
        recipes.update(o.get("event_recipes") or {})
        ingredients.update(o.get("event_ingredients") or {})
    return services, recipes, ingredients


def context(rule, state=None, pool=None, placed=None):
    data = {
        name: copy.deepcopy(getattr(f, name))
        for name in [
            "KITCHEN",
            "INGREDIENTS",
            "STOCK",
            "RECIPES",
            "BASE_SERVICES",
            "DELIVERIES",
        ]
    }
    for role, label in ROLE_LABELS.items():
        if role in data["INGREDIENTS"]:
            data["INGREDIENTS"][role]["label"] = label
    state = state or {}
    if placed:
        services, recipes, ingredients = placed
        data["BASE_SERVICES"] = data["BASE_SERVICES"] + copy.deepcopy(services)
        data["RECIPES"].update(copy.deepcopy(recipes))
        for role, item in ingredients.items():
            data["INGREDIENTS"].setdefault(role, copy.deepcopy(item))
            data["STOCK"].setdefault(role, 0)
    data["RECIPES"].update(copy.deepcopy(state.get("custom_recipes") or {}))
    for role, item in (state.get("custom_ingredients") or {}).items():
        data["INGREDIENTS"][role] = copy.deepcopy(item)
        data["STOCK"].setdefault(role, 0)
    for role, amount in (pool or {}).items():
        data["STOCK"][role] = round(data["STOCK"].get(role, 0) + amount, 6)
    data["KITCHEN"]["budget"] = rule["weekly_limit"]
    data["KITCHEN"]["same_allergens"] = rule["same_allergens"]
    data["KITCHEN"]["policy"] = {
        "free_from": rule["allergens"],
        "strict_may_contain": True,
    }
    return SimpleNamespace(**data)


def build(state, fresh=False, progress=None, book=None, rule=None):
    rule = rule or rules()[0]
    book = book if book is not None else ledger()[0]
    others = week_orders(book, state.get("id"))
    week_placed, month_spent = spend(book, state.get("id"))
    pool = {}
    for o in others:
        for role, amount in (o.get("bought") or {}).items():
            pool[role] = pool.get(role, 0) + amount
    placed = placed_events(others)
    ctx = context(rule, state, pool, placed)
    if state.get("increment"):
        # An outside assistant orders on top of the kitchen's standing week, so
        # both channels see the same stock position for the same request.
        plan = k.build({**k.initial_state(), "budget": 1e12}, context=context(rule, None, pool, placed))
        for r in plan["rows"]:
            if r["role"] != "extra":
                ctx.STOCK[r["role"]] = round(ctx.STOCK.get(r["role"], 0) + r["ordered"], 6)
    state["budget"] = 1e12  # limits are cumulative and owned here, not per sheet
    kept = [c for c in state.get("calls", [])]
    out = k.build(state, fresh=fresh, context=ctx, progress=progress)
    state["calls"] = [c for c in state["calls"] if c.get("method") != "CACHE"] if fresh else kept
    out["evidence"]["calls"] = state["calls"]
    checks = out["checks"]
    rows = {r["id"]: r for r in out["rows"]}
    notes = list((state.get("reading") or {}).get("assumptions") or [])
    if not any(r["units"] > 0 for r in out["rows"]) and not checks and not state.get("line_checks"):
        checks.append(
            {
                "id": "empty",
                "kind": "gap",
                "text": "Everything for week 47 is already ordered or in stock. Add a meal or a product to order more."
                if others
                else "There is nothing to order. Add a meal or a product first.",
                "row_ids": [],
                "can_approve": False,
            }
        )
    if not rule["ask_swap"]:
        checks[:] = [c for c in checks if c["kind"] != "swap"]
    if rule["same_allergens"]:
        for row in out["rows"]:
            original = (
                load().get(f.INGREDIENTS[row["role"]]["ids"][0])
                if row["role"] in f.INGREDIENTS
                else None
            )
            if (
                original
                and row["change"] == "Swapped"
                and (
                    set(row["contains"]) - set(original["contains"])
                    or set(row["may_contain"]) - set(original["may_contain"])
                )
            ):
                checks.append(
                    {
                        "id": "allergen-" + row["id"],
                        "kind": "gap",
                        "text": "This swap adds an allergen. Choose a different product.",
                        "row_ids": [row["id"]],
                        "can_approve": False,
                    }
                )
    # Assumed recipes, banned twists and guest diets from the request.
    services = out["services"]
    for key, recipe in (state.get("custom_recipes") or {}).items():
        if not any(s["recipe"] == key for s in services):
            continue
        ids = [r["id"] for r in out["rows"] if any(a.get("recipe") == key for a in r["allocations"])]
        labels = {**ROLE_LABELS, **{role: i.get("label", role) for role, i in (state.get("custom_ingredients") or {}).items()}}
        parts = ", ".join(f"{labels.get(role, role)} {amount:g} {'ml' if ctx.INGREDIENTS.get(role, {}).get('unit') == 'l' else 'g'}" for role, amount in recipe["ingredients"].items())
        checks.append(
            {
                "id": key,
                "kind": "assumed",
                "title": f"Assumed recipe: {recipe['name']}",
                "text": f"{recipe['name']} is not in your recipes, so Valio assumed one. Per guest: {parts}. Please check it before you approve.",
                "row_ids": ids,
                "can_approve": True,
            }
        )
    for ev in state.get("menu_events") or []:
        for dish in ev["dishes"]:
            banned = [a for a in dish.get("modifier_allergens") or [] if a in rule["allergens"]]
            if not banned:
                continue
            ids = [r["id"] for r in out["rows"] if any(a.get("recipe") == dish["recipe"] and a.get("date") == ev["date"] and a.get("wedding") for a in r["allocations"])]
            checks.append(
                {
                    "id": "twist-" + ev["id"][:8] + "-" + dish["recipe"],
                    "kind": "allergen",
                    "title": f"{dish.get('name', 'Dish')}: {dish['modifier']} left out",
                    "text": f"“{dish.get('name', 'This dish')} with {dish['modifier']}” contains {' and '.join(banned)}, and your kitchen rule is no {' or '.join(banned)}. Valio left the {dish['modifier']} out and prepared your standard {dish.get('name', 'recipe').lower()}. Approve this, or change the dish.",
                    "row_ids": ids,
                    "can_approve": True,
                }
            )
    cat = load()
    if rule["allergens"]:
        unknown = [r for r in out["rows"] if r["units"] > 0 and (cat.get(r["product_id"]) or {}).get("undeclared")]
        if unknown:
            checks.append(
                {
                    "id": "undeclared-" + "-".join(sorted(r["id"] for r in unknown))[:60],
                    "kind": "allergen",
                    "title": "No allergen information from the supplier",
                    "text": f"{', '.join(r['name'] for r in unknown[:4])} {'come' if len(unknown) > 1 else 'comes'} with no allergen declaration, and your kitchen rule is no {' or '.join(rule['allergens'])}. Check the label before serving, then approve.",
                    "row_ids": [r["id"] for r in unknown],
                    "can_approve": True,
                }
            )
    for need in state.get("dietary") or []:
        a, word = need["allergen"], ALLERGEN_WORDS.get(need["allergen"], need["allergen"])
        if a in rule["allergens"]:
            notes.append(f"{need['label'].capitalize()}: your kitchen rule already excludes {a}, including may-contain. All {sum(r['units'] > 0 for r in out['rows'])} products on this order were checked by their allergen declarations and names" + (", and the ones with no declaration need your OK." if any(c["id"].startswith("undeclared-") for c in checks) else "."))
            continue
        def has(prod):
            return ("milk" in prod.get("contains", []) and not prod.get("lactose_free")) if a == "lactose" else a in prod.get("contains", [])
        hit = []
        for r in out["rows"]:
            p = cat.get(r["product_id"]) or {}
            if r["units"] > 0 and has({**p, "contains": r["contains"]}) and any(x.get("date") == need.get("date") and x.get("wedding") for x in r["allocations"]):
                hit.append(r)
        dishes = sorted({x["dish"] for r in hit for x in r["allocations"] if x.get("date") == need.get("date") and x.get("wedding")})
        # Ingredients the kitchen already has in stock are not on the order, but the guests still eat them.
        ordered_roles = {r["role"] for r in hit}
        for ev in state.get("menu_events") or []:
            if ev.get("date") != need.get("date") or (need.get("event_id") and ev.get("id") != need.get("event_id")):
                continue
            for dish in ev["dishes"]:
                for role in (ctx.RECIPES.get(dish.get("recipe")) or {}).get("ingredients", {}):
                    ids = (ctx.INGREDIENTS.get(role) or {}).get("ids") or []
                    prod = cat.get(ids[0]) if ids else None
                    if prod and role not in ordered_roles and has(prod):
                        ordered_roles.add(role)
                        hit.append({"id": None, "name": f"{ROLE_LABELS.get(role, role)} from your stock", "role": role})
                        dishes = sorted(set(dishes) | {dish.get("name") or ctx.RECIPES[dish["recipe"]]["name"]})
        if not hit:
            notes.append(f"{need['label'].capitalize()}: no product for this meal contains {word}, including what comes from your stock.")
            continue
        who = f"{need['guests']} portions" if need.get("guests") else "their portions"
        checks.append(
            {
                "id": "diet-" + a + "-" + (need.get("event_id") or "")[:8],
                "kind": "diet",
                "title": need["label"].capitalize(),
                "text": f"{', '.join(dishes)} {'use' if len(dishes) > 1 else 'uses'} {', '.join(r['name'] for r in hit[:4])}, which contain {word}. Plate {who} without them, or tell Valio a separate dish for these guests.",
                "row_ids": [r["id"] for r in hit if r["id"]],
                "can_approve": True,
            }
        )
    for line in state.get("line_checks") or []:
        present = [rid for rid in line["row_ids"] if rid in rows and rows[rid]["units"] > 0]
        if line["row_ids"] and not present:
            continue
        checks.append({**copy.deepcopy(line), "row_ids": present})
    total = out["total"]
    limit, monthly = rule["weekly_limit"], rule["monthly_limit"]
    all_ids = [r["id"] for r in out["rows"]]
    over = round(week_placed + total - limit, 2)
    if total > 0 and over > 0:
        blocked = rule["over_limit"] == "block"
        checks.append(
            {
                "id": "budget",
                "kind": "budget",
                "title": f"{eur(over)} over your {eur(limit)} weekly limit",
                "text": "Your rule does not allow orders over the weekly limit. Change the order, or change the rule in Settings."
                if blocked
                else (
                    f"{eur(week_placed)} is already placed for week 47. This order takes the week to {eur(week_placed + total)}. An approval covers only these products, quantities and prices."
                    if week_placed
                    else f"This order totals {eur(total)}. An approval covers only these products, quantities and prices. Your limit stays the same."
                ),
                "row_ids": all_ids,
                "can_approve": not blocked,
            }
        )
    over_month = round(month_spent + total - monthly, 2)
    if total > 0 and over_month > 0:
        blocked = rule["over_limit"] == "block"
        checks.append(
            {
                "id": "monthly",
                "kind": "budget",
                "title": f"{eur(over_month)} over your {eur(monthly)} monthly limit",
                "text": ("Your rule does not allow orders over the monthly limit. Change the order, or change the rule in Settings." if blocked else f"November spend is {eur(month_spent)}. This order takes it to {eur(month_spent + total)}."),
                "row_ids": all_ids,
                "can_approve": not blocked,
            }
        )
    mine = {r["product_id"] for r in out["rows"] if r["units"] > 0}
    for o in others:
        same = mine & set(o.get("product_ids") or [])
        if mine and len(same) * 2 >= len(mine) and (len(same) >= 3 or len(same) == len(mine)):
            checks.append(
                {
                    "id": "duplicate-" + o["order_number"],
                    "kind": "duplicate",
                    "title": f"Possible repeat of order {o['order_number']}",
                    "text": f"Order {o['order_number']} for week 47 already has {len(same)} of these {len(mine)} products. Approve only if you want them a second time.",
                    "row_ids": all_ids,
                    "can_approve": True,
                }
            )
            break
    if others and total > 0:
        notes.append(f"This is an additional order for week 47. Already placed: {eur(week_placed)} in {len(others)} order{'s' if len(others) > 1 else ''}.")
    growth = total - state.get("baseline_total", total)
    if growth > rule["growth_limit"] and not any(c["kind"] == "budget" for c in checks):
        checks.append(
            {
                "id": "growth",
                "kind": "budget",
                "title": f"Bigger change: {eur(growth)}",
                "text": f"This order {'is' if not state.get('baseline_total') else 'grew by'} {eur(growth)}. Your rule asks for an OK above {eur(rule['growth_limit'])}.",
                "can_approve": True,
                "row_ids": all_ids,
            }
        )
    if state.get("keep_original"):
        checks.append(
            {
                "id": "keep-original",
                "kind": "gap",
                "text": "The original fish cannot arrive before the meal. Change the menu or accept the available fish.",
                "row_ids": [],
                "can_approve": False,
            }
        )
    for c in checks:
        c["fingerprint"] = k.digest(
            [
                rule,
                c["id"],
                c.get("title"),
                [
                    [
                        rid,
                        rows[rid]["product_id"],
                        rows[rid]["units"],
                        rows[rid]["unit_price"],
                    ]
                    for rid in c["row_ids"]
                    if rid in rows
                ],
            ]
        )
        ack = state["approvals"].get(c["id"])
        c["approved"] = bool(
            c["can_approve"] and ack and ack["fingerprint"] == c["fingerprint"]
        )
        c["approved_at"] = ack.get("at") if c["approved"] else None
        c["approved_by"] = ack.get("by", "Sanna") if c["approved"] else None
        c["reopened"] = bool(ack and not c["approved"])
    out.update(
        pending=sum(not c["approved"] for c in checks),
        can_place=all(c["approved"] for c in checks),
        rules=rule,
        budget=limit,
        week_placed=week_placed,
        month_spent=month_spent,
        monthly_limit=monthly,
        notes=notes,
        source=state.get("source"),
        request=state.get("request", ""),
        request_at=state.get("request_at"),
        reading=state.get("reading"),
        baseline_total=state.get("baseline_total", out["total"]),
        previous_total=state.get(
            "previous_total", state.get("baseline_total", out["total"])
        ),
        draft_id=state.get("id"),
        status=state.get("status", "draft"),
    )
    for row in out["rows"]:
        old = next(
            (r for r in state.get("previous_rows", []) if r["id"] == row["id"]), None
        )
        row["previous_units"] = old["units"] if old else None
    return out


def slim(o):
    """What the screens need. The full evidence stays on the server until asked for."""
    if not isinstance(o, dict) or "rows" not in o:
        return o
    out = {key: v for key, v in o.items() if key not in ("evidence", "kitchen", "stock", "recipes", "services")}
    return out


def receipt(draft_id):
    o = get_draft(draft_id)
    return {"calls": o["evidence"]["calls"], "decisions": o["evidence"].get("decisions", []), "events": o["evidence"].get("events", [])}


def new_draft(services=None, source="Sanna Virtanen", increment=False):
    state = k.initial_state()
    state.update(
        id=uuid.uuid4().hex, status="draft", source=source, request="", request_at=now()
    )
    if services is not None:
        state["services_override"] = services
    if increment:
        state["increment"] = True
    out = build(state, fresh=True)
    state["baseline_total"] = out["total"] if services is None and not increment else 0
    state["baseline_rows"] = copy.deepcopy(out["rows"])
    out = build(state)
    Store().put("drafts/" + state["id"], state)
    out["draft_id"] = state["id"]
    if not increment:
        index_draft(state, out)
    return out


def draft(draft_id):
    if (
        not isinstance(draft_id, str)
        or len(draft_id) != 32
        or not all(c in "0123456789abcdef" for c in draft_id)
    ):
        raise k.KitchenError("There is no order with that id in this account. Use the draft_id that order_products or prepare_order returned.")
    state, version = Store().get("drafts/" + draft_id)
    if not state:
        raise k.KitchenError("There is no order with that id in this account. Use the draft_id that order_products or prepare_order returned.")
    return state, version


def get_draft(draft_id):
    state, _ = draft(draft_id)
    book = ledger()[0]
    committed = committed_order(draft_id, book)
    if committed:
        return committed
    if state["status"] == "placed":
        return state["placed_order"]
    return build(state, book=book)


def shorten(text, n):
    """Cut at a word boundary, never mid-word."""
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


def check_label(c):
    return c.get("title") or {"swap": "Product swap", "pack": "Larger pack"}.get(c["kind"]) or shorten(c["text"].split(". ")[0], 90)


def change(draft_id, action, value=None, by="Sanna Virtanen"):
    state, version = draft(draft_id)
    book = ledger()[0]
    if state["status"] != "draft" or committed_order(draft_id, book):
        raise k.KitchenError(
            "This order is already placed. Start another order to change it."
        )
    rule = rules()[0]
    logged = None
    if action == "approve":
        out = build(state, book=book, rule=rule)
        c = next((c for c in out["checks"] if c["id"] == value), None)
        if not c or not c["can_approve"]:
            raise k.KitchenError(
                "Change the menu or quantity before placing this order."
            )
        if value == "swap":
            state["keep_original"] = False
        stamp = dt.datetime.now(k.TZ)
        state["approvals"][value] = {
            "fingerprint": c["fingerprint"],
            "at": stamp.strftime("%H:%M"),
            "time": stamp.isoformat(),
            "by": by.split()[0],
            "label": check_label(c),
        }
        logged = event(f"{by.split()[0]} approved: {check_label(c)}", note="Approval on the week 47 draft", by=by, total=out["total"], link="/orders/draft-" + draft_id)
        if value == "swap":
            out = build(state, book=book, rule=rule)
        else:
            c.update(approved=True, approved_at=stamp.strftime("%H:%M"), approved_by=by.split()[0], reopened=False)
            out.update(pending=sum(not x["approved"] for x in out["checks"]), can_place=all(x["approved"] for x in out["checks"]))
        result = out
    else:
        if action == "unapprove":
            old = state["approvals"].pop(value, None)
            if old:
                logged = event(f"{by.split()[0]} withdrew an approval: {old.get('label', value)}", note="Approval withdrawn", by=by)
        elif action == "quantity":
            n = value.get("units") if isinstance(value, dict) else None
            if type(n) is not int or not 0 <= n <= 9999:
                raise k.KitchenError("Use a whole number of packs from 0 to 9999.")
            state["overrides"][str(value.get("id"))] = n
        elif action == "small-cream":
            state["small_cream"] = True
        elif action == "keep-original":
            # There is no safe path to order unavailable fish. Keeping it keeps the order blocked.
            state["keep_original"] = True
        elif action == "restore":
            state["overrides"].pop(value, None)
        elif action == "remove-extra":
            state["extra"] = [e for e in state["extra"] if e["product_id"] != str(value)]
        elif action == "add":
            item = value if isinstance(value, dict) else {"product_id": value}
            pid = str(item.get("product_id"))
            day = item.get("delivery") if item.get("delivery") in f.DELIVERIES else f.DELIVERIES[-1]
            extra = next((e for e in state["extra"] if e["product_id"] == pid), None)
            if extra:
                extra["units"] = state["overrides"].pop("extra-" + pid, extra["units"]) + 1
            else:
                state["extra"].append({"product_id": pid, "units": 1, "delivery": day})
        else:
            raise k.KitchenError("That change is not supported.")
        result = build(state, book=book, rule=rule)
        if action == "quantity" and str(value.get("id")) not in {r["id"] for r in result["rows"]}:
            raise k.KitchenError("That product is no longer on this order.")
    state["events"].append(
        {"action": action, "value": value, "at": now(), "by": by.split()[0]}
    )
    Store().put("drafts/" + draft_id, state, version)
    if logged or action not in ("approve", "unapprove"):
        def apply(b):
            if logged:
                b["events"].insert(0, logged)
            set_index(b, state, result)
        update_ledger(apply)
    return result


def apply_request(
    draft_id,
    text=None,
    media=None,
    source="text",
    progress=None,
    parsed=None,
    replace_event_id=None,
):
    from . import portal_intake as intake

    state, version = draft(draft_id)
    book = ledger()[0]
    if state["status"] != "draft" or committed_order(draft_id, book):
        raise k.KitchenError("This order has already been placed.")
    rule = rules()[0]
    calls = []
    if parsed:
        reading = parsed
        reading.setdefault("kind", "close" if reading.get("action") == "close" else "menu")
        reading.setdefault("date", "2026-11-21")
        reading.setdefault("event", "Wedding")
        for d in reading.get("dishes", []):
            d.setdefault("name", f.RECIPES.get(d.get("recipe"), {}).get("name", "Dish"))
    elif source == "text":
        reading = intake.understand_order(text, rule)
        if reading.get("question"):
            return {"question": reading["question"], "draft_id": draft_id}
    else:
        reading = understand(text=text, media=media, source=source)
        reading.update(kind="menu", products=[], dietary=[], assumptions=[])
        for d in reading.get("dishes", []):
            d["name"] = f.RECIPES[d["recipe"]]["name"]
        call = reading.pop("_call", None)
        if call:
            calls.append(call)
    if reading.get("call"):
        calls.append(reading.pop("call"))
    if progress:
        progress("read", reading)
    if reading["status"] != "readable":
        return {
            "reading": reading,
            "question": reading.get("reason") or "How many guests and which dishes?",
            "draft_id": draft_id,
        }
    before = build(state, book=book, rule=rule)
    earlier = (state.get("previous_rows"), state.get("previous_total"))
    state["previous_rows"] = copy.deepcopy([{key: v for key, v in r.items() if key not in ("allocations", "options")} for r in before["rows"]])
    state["previous_total"] = before["total"]
    state["request"] = reading["transcript"]
    state["request_at"] = now()
    state["reading"] = reading
    state["calls"] = calls
    state["line_checks"] = []
    if reading.get("kind") == "close":
        state["services_override"] = [
            service
            for service in k.services_for(state, context(rule, state))
            if service["date"] != reading["date"] and not service.get("wedding")
        ]
        state["menu_events"] = [e for e in state.get("menu_events") or [] if e["date"] != reading["date"]]
    if reading.get("dishes"):
        recipes, ingredients = intake.plan_recipes(reading, rule, calls)
        state.setdefault("custom_recipes", {}).update(recipes)
        state.setdefault("custom_ingredients", {}).update(ingredients)
        ev = {
            "date": reading["date"],
            "event": reading.get("event", "Kitchen change"),
            "covers": reading["covers"],
            "dishes": reading["dishes"],
            "transcript": reading["transcript"],
            "from_photo": source == "photo",
        }
        events = state.setdefault("menu_events", [])
        if (
            source == "photo"
            and "wedding" in ev["event"].casefold()
            and not replace_event_id
        ):
            previous_wedding = next(
                (
                    item
                    for item in events
                    if item["date"] == ev["date"]
                    and "wedding" in item.get("event", "Wedding").casefold()
                ),
                None,
            )
            if previous_wedding:
                replace_event_id = previous_wedding.get("id")
        target = (
            next((e for e in events if e.get("id") == replace_event_id), None)
            if replace_event_id
            else next(
                (
                    e
                    for e in events
                    if e["date"] == ev["date"]
                    and e.get("event", "Wedding").casefold()
                    == ev["event"].casefold()
                ),
                None,
            )
        )
        ev["id"] = target.get("id", uuid.uuid4().hex) if target else uuid.uuid4().hex
        if target:
            events[events.index(target)] = ev
        else:
            events.append(ev)
        state["wedding"] = ev
        reading["event_id"] = ev["id"]
        state["dietary"] = [d for d in state.get("dietary") or [] if d.get("event_id") != ev["id"]]
    for need in reading.get("dietary") or []:
        state.setdefault("dietary", []).append({**need, "date": reading.get("date"), "event_id": reading.get("event_id")})
    if reading.get("products"):
        lines = intake.plan_products(reading, rule, calls)
        for n, line in enumerate(lines):
            need = line["need"]
            unit = "L" if need["unit"] == "l" else need["unit"]
            asked = f"{need['quantity']:,.0f} {unit} {need['name'].lower()}"
            ids = []
            for pick in line["chosen"]:
                option = next(o for o in line["options"] if o["product_id"] == pick["product_id"])
                state["extra"] = [e for e in state["extra"] if e["product_id"] != pick["product_id"]]
                state["overrides"].pop("extra-" + pick["product_id"], None)
                got = pick["units"] * option["pack"]
                state["extra"].append(
                    {
                        "product_id": pick["product_id"],
                        "units": pick["units"],
                        "delivery": line["delivery"],
                        "need": need,
                        "options": line["options"],
                        "compared": line["compared"],
                        "why": "requested",
                        "reason": f"You asked for {asked} by {nice_day(need['date'])}. {pick['units']:,} × {option['pack']:g} {intake.unit_word(option['pack_unit'])} = {got:,.0f} {intake.unit_word(option['pack_unit'])}. "
                        + (f"Valio compared {line['compared']} matching products on live price and stock. {option.get('note', '')}." if line["compared"] > 1 else "This is the product you named."),
                    }
                )
                ids.append("extra-" + pick["product_id"])
            when = nice_day(need["date"])
            if not line["chosen"]:
                closest = "; ".join(f"{o['name']}: {o.get('note', 'not available')}" for o in line["options"][:3])
                blocked = next((x.get("blocked") for x in reading["products"] if x["name"] == need["name"] and x.get("blocked")), None)
                title = f"No {need['name'].lower()} can arrive by {when}" if line["options"] else f"{need['name'].capitalize()}: your rule is no {blocked.split(' (')[0].split()[-1]}" if blocked else f"“{need['name']}” is not in Valio's catalogue"
                state["line_checks"].append({"id": f"line-none-{n}", "kind": "gap", "title": title, "text": (f"Valio checked {line['compared']} matching products. Closest: {closest}. Ask for a later day or another product." if line["options"] else (f"Valio has {need['name'].lower()}, but it {blocked.split(' (')[0]} and your kitchen rule is no {blocked.split(' (')[0].split()[-1]}. Choose another product, or change the rule in Settings." if blocked else f"Valio found no product matching “{need['name']}” that fits your kitchen rules. Try other words, or search the catalogue.")), "row_ids": [], "can_approve": False})
            elif line["short"] > 0:
                state["line_checks"].append({"id": f"line-short-{n}", "kind": "partial", "title": f"Only part of the {need['name'].lower()} can arrive by {when}", "text": f"You asked for {asked}. Valio has {need['quantity'] - line['short']:,.0f} {unit} that can arrive in time; {line['short']:,.0f} {unit} are short. Approve the part delivery, or ask for a later day.", "row_ids": ids, "can_approve": True})
            elif line["split"]:
                state["line_checks"].append({"id": f"line-split-{n}", "kind": "partial", "title": f"{need['name'].capitalize()} split across {len(ids)} products", "text": f"No single product has {asked} in stock for {when}, so Valio filled it from the cheapest products first.", "row_ids": ids, "can_approve": True})
            if line["chosen"] and (need["quantity"] >= HUGE[need["unit"]] or sum(
                    p["units"] * next(o for o in line["options"] if o["product_id"] == p["product_id"])["unit_price"] for p in line["chosen"]) >= 5000):
                state["line_checks"].append({"id": f"line-huge-{n}", "kind": "quantity", "title": f"Check the amount: {asked}",
                    "text": f"{asked.capitalize()} is far more than {f.KITCHEN.get('name', 'your kitchen')} usually orders at once. Check the amount before you approve, so a typing slip doesn't become a delivery.",
                    "row_ids": ids, "can_approve": True})
    if state.get("menu_events") is not None:
        state["wedding"] = state["menu_events"][-1] if state["menu_events"] else None
    state["overrides"] = {key: v for key, v in state["overrides"].items() if key.startswith("extra-")}
    state["keep_original"] = False
    out = build(state, fresh=True, progress=progress, book=book, rule=rule)
    same = lambda rows: sorted((r["id"], r["product_id"], r["units"]) for r in rows)
    if earlier[0] is not None and same(out["rows"]) == same(before["rows"]) and len(out["checks"]) == len(before["checks"]):
        # Saying the same thing twice changes nothing: keep showing what the first request changed.
        state["previous_rows"], state["previous_total"] = earlier
        out = build(state, book=book, rule=rule)
        out["unchanged"] = True
    if progress:
        progress("allergens", out)
        progress("budget", out)
    Store().put("drafts/" + draft_id, state, version)
    if not state.get("increment") or out["rows"]:
        index_draft(state, out)
    return out


def ledger():
    doc, version = Store().get("ledger")
    return doc or {"orders": [], "events": []}, version


def set_index(book, state, out):
    if any(o["draft_id"] == state["id"] for o in book["orders"]):
        return
    entry = {
        "draft_id": state["id"],
        "order_number": "Week 47",
        "placed_by": state["source"],
        "placed_at": state["request_at"],
        "deliveries": [{"date": d["date"]} for d in out["deliveries"]],
        "total": out["total"],
        "products": sum(r["units"] > 0 for r in out["rows"]),
        "pending": out["pending"],
        "status": "Draft",
        "request": state.get("request", ""),
    }
    entries = book.setdefault("drafts", [])
    existing = next(
        (i for i, d in enumerate(entries) if d["draft_id"] == state["id"]), None
    )
    if existing is None:
        entries.insert(0, entry)
    else:
        entries[existing] = entry


def index_draft(state, out):
    update_ledger(lambda book: set_index(book, state, out))


def committed_order(draft_id, book=None):
    book = book if book is not None else ledger()[0]
    entry = next((o for o in book["orders"] if o["draft_id"] == draft_id), None)
    if not entry:
        return None
    if entry.get("snapshot_key"):
        snapshot, _ = Store().get(entry["snapshot_key"])
        if not snapshot:
            raise k.KitchenError(
                "This order was placed. Its receipt is temporarily unavailable. Try again."
            )
        return snapshot
    # Compatibility with confirmations made before immutable commit snapshots.
    state, _ = draft(draft_id)
    if state["status"] == "placed":
        return state["placed_order"]
    raise k.KitchenError(
        "This order was already placed. Open Orders to review its recorded total."
    )


def place(draft_id, assistant=False):
    state, version = draft(draft_id)
    if assistant and state["source"] != "Aurora Group assistant":
        raise k.KitchenError(
            "Prepare this order through the connected assistant first."
        )
    book = ledger()[0]
    committed = committed_order(draft_id, book)
    if committed:
        return committed
    if state["status"] == "placed":
        return state["placed_order"]
    out = build(state, fresh=True, book=book)
    by = "Aurora Group assistant" if assistant else "Sanna Virtanen"
    if state.get("keep_original") or not out["can_place"]:
        open_checks = [check_label(c) for c in out["checks"] if not c["approved"]]
        if assistant:
            Store().put("drafts/" + draft_id, state, version)
            index_draft(state, out)
            log_event(
                f"Aurora Group assistant prepared an order that needs your OK",
                note="Not placed: " + "; ".join(open_checks[:3]),
                by=by, total=out["total"], link="/orders/draft-" + draft_id,
            )
            raise k.KitchenError(
                "This order needs a person to approve it before it can be placed: "
                + "; ".join(open_checks[:3])
                + f". Ask the head chef to review it at {SITE}/orders/draft-{draft_id}"
            )
        raise k.KitchenError(
            "This order changed since you approved it. Check the items that need your OK, then place it again."
        )
    # Private demo copies share draft ids with their template, so the number also depends on the account.
    oid = "AU-" + (draft_id[:8] if account_id() == "aurora" else hashlib.sha256((account_id() + draft_id).encode()).hexdigest()[:8]).upper()
    approvals = [
        {"label": check_label(c), "by": c["approved_by"], "at": c["approved_at"]}
        for c in out["checks"]
    ]
    note = "Within your rules, no approval needed" if not approvals else f"{len(approvals)} approval{'s' if len(approvals) > 1 else ''} by {approvals[0]['by']}: " + "; ".join(a["label"] for a in approvals)
    out.update(
        status="placed",
        order_number=oid,
        placed_by=by,
        prepared_by=state["source"],
        placed_at=now(),
        week=47,
        within_rules=not approvals,
        approvals=approvals,
        rule_note=note,
        confirmation={"order_number": oid, "at": now(), "demo": True},
    )
    # The immutable snapshot exists before its pointer can be committed to the ledger.
    # The successful conditional ledger write is the only commitment point.
    snapshot_key = "orders/" + draft_id + "/" + uuid.uuid4().hex
    Store().put(snapshot_key, out)
    bought = {}
    for r in out["rows"]:
        if r["role"] != "extra" and r["units"] > 0:
            bought[r["role"]] = round(bought.get(r["role"], 0) + r["ordered"], 6)
    entry = {
        "order_number": oid,
        "draft_id": draft_id,
        "snapshot_key": snapshot_key,
        "placed_by": by,
        "prepared_by": state["source"],
        "placed_at": out["placed_at"],
        "total": out["total"],
        "products": sum(r["units"] > 0 for r in out["rows"]),
        "product_ids": [r["product_id"] for r in out["rows"] if r["units"] > 0],
        "bought": bought,
        # What this order's events will use, so later orders don't count that stock as free.
        "event_services": [
            {**{key: sv[key] for key in ("date", "recipe", "covers") if key in sv}, "recipe": placed_key(draft_id, sv["recipe"], state)}
            for sv in k.services_for(state) if sv.get("wedding")
        ],
        "event_recipes": {placed_key(draft_id, key, state): r for key, r in (state.get("custom_recipes") or {}).items()},
        "event_ingredients": copy.deepcopy(state.get("custom_ingredients") or {}),
        "request": state.get("request", ""),
        "deliveries": [
            {
                "date": d["date"],
                "subtotal": d["subtotal"],
                "cutoff": d["cutoff"],
                "rows": [{"id": r["id"]} for r in d["rows"] if r["units"] > 0],
            }
            for d in out["deliveries"]
        ],
        "status": "Placed",
        "week": 47,
        "within_rules": not approvals,
        "rule_note": note,
    }
    for attempt in range(5):
        book, etag = ledger()
        committed = committed_order(draft_id, book)
        if committed:
            return committed
        book["orders"].insert(0, entry)
        book["drafts"] = [d for d in book.get("drafts", []) if d["draft_id"] != draft_id]
        book["events"].insert(
            0,
            {**event(f"{by} placed order {oid}", note=note, by=by, total=out["total"], link="/orders/" + oid), "order": oid},
        )
        try:
            Store().put("ledger", book, etag)
            break
        except Conflict:
            if attempt == 4:
                raise
    # This draft is only a convenience copy. A failed write cannot change commitment.
    state.update(status="placed", placed_order=out)
    try:
        Store().put("drafts/" + draft_id, state, version)
    except (Conflict, k.KitchenError, httpx.HTTPError):
        pass
    return out


def mcp_token(regenerate=False):
    doc, version = Store().get("mcp")
    if doc and not regenerate:
        return doc["token"]
    scope = base64.urlsafe_b64encode(account_id().encode()).decode().rstrip("=")
    token = "vat_" + scope + "." + secrets.token_urlsafe(24)
    Store().put("mcp", {"token": token, "created_at": now()}, version)
    if doc:
        log_event("Sanna replaced the connected-assistant access token", note="The old token stopped working")
    return token


def token_account(token):
    """Account id encoded in a well-formed token, or None. The secret is checked separately."""
    m = re.fullmatch(r"vat_([A-Za-z0-9_-]{4,80})\.([A-Za-z0-9_-]{20,64})", token or "")
    if not m:
        return None
    try:
        acct = base64.urlsafe_b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    return acct if acct == "aurora" or re.fullmatch(r"(?:test|demo)-[a-f0-9]{32}", acct) else None


def token_valid(token):
    doc, _ = Store().get("mcp")
    return bool(doc) and hmac.compare_digest(doc["token"], token)


def account():
    rule, _ = rules()
    book, _ = ledger()
    week, month = spend(book)
    return {
        "name": account_name(),
        "account_id": account_id(),
        "team": f.TEAM,
        "rules": rule,
        "orders": book["orders"],
        "drafts": [d for d in book.get("drafts", []) if d["status"] == "Draft"],
        "events": book["events"][:40],
        "bookings": f.KITCHEN["bookings"],
        "recipes": f.RECIPES,
        "ingredient_names": ROLE_LABELS,
        "ingredient_units": {role: i["unit"] for role, i in f.INGREDIENTS.items()},
        "stock": f.STOCK,
        "menu": f.BASE_SERVICES,
        "week_placed": week,
        "month_spent": month,
        "mcp_url": SITE + "/mcp/",
        "mcp_token": mcp_token(),
    }


CLAIMS = [
    ("lactose_free", r"lactose[\s-]*free|laktoositon\w*"),
    ("gluten_free", r"gluten[\s-]*free|gluteeniton\w*"),
    ("vegan", r"vegan\w*|vegaani\w*"),
]
CATEGORY_HINTS = {"milk": "10400", "maito": "10400", "cream": "10401", "kerma": "10401"}


def search(query):
    rule, _ = rules()
    cat = load()
    text = (query or "").strip()
    flags = {}
    for flag, pattern in CLAIMS:
        if re.search(pattern, text, re.I):
            flags[flag] = True
            text = re.sub(pattern, " ", text, flags=re.I)
    words = text.split()
    if text and cat.get(text):
        ps = [cat.get(text)]
    else:
        base = " ".join(words) or ("maito milk" if flags else "Valio maito")
        ps = [p for p, _ in cat.search(base, k=120)]
        if flags.get("lactose_free"):
            ps = [p for p in ps if p.get("lactose_free")]
        if flags.get("gluten_free"):
            ps = [p for p in ps if p.get("gluten_free")]
        if flags.get("vegan"):
            ps = [p for p in ps if p.get("vegan")]
        hint = next((CATEGORY_HINTS[w.lower()] for w in words if w.lower() in CATEGORY_HINTS), "10400" if not words else None)
        if hint:
            ps.sort(key=lambda p: p["category"] != hint)  # stable: the plain product first
        ps = ps[:24]
    api = ValioAPI()
    ids = [p["id"] for p in ps]
    day = f.DELIVERIES[0]
    prices = api.price(day, ids) if ids else {}
    stock = api.availability(day, ids) if ids else {}
    policy = {"free_from": rule["allergens"], "strict_may_contain": True}
    out = []
    for p in ps:
        pr = prices.get(p["id"], {})
        av = stock.get(p["id"], {})
        if pr.get("unit_price") is None:
            continue
        violations = product_violations(p, policy=policy)
        delivery = next((d for d in f.DELIVERIES if d >= (av.get("available_date") or "9999")), None)
        if violations:
            reason = "Kitchen rule: " + violations[0].split(" (")[0]
        elif not av.get("orderable"):
            reason = "Out of stock at Valio"
        elif not delivery:
            reason = "Cannot arrive in week 47"
        elif k.cutoff_passed(av.get("closing_time")):
            closed = dt.datetime.fromisoformat(av["closing_time"].replace("Z", "+00:00")).astimezone(k.TZ)
            reason = f"Order-by time passed {closed.strftime('%a')} {closed.day} {closed.strftime('%b %H:%M')}"
        else:
            reason = ""
        out.append(
            {
                **{key: p.get(key) for key in ["id", "name", "name_fi", "brand", "pack", "pack_dim", "sales_unit", "contains", "may_contain", "lactose_free", "gluten_free", "vegan", "labels", "origin", "reliability", "co2_per_kg"]},
                **pr,
                "availability": av,
                "delivery": delivery,
                "allowed": not reason,
                "reason": reason,
            }
        )
    out.sort(key=lambda p: not p["allowed"])  # stable: what can be ordered first
    return {"products": out, "calls": api.audit}


# ---- outside assistants (MCP) ------------------------------------------


def assistant_request(text, parsed=None):
    """Same reading, recipes, stock position and rules as Ask Valio in the portal."""
    from . import portal_intake as intake

    reading = parsed or intake.understand_order(text, rules()[0])
    if reading.get("question"):
        return {"question": reading["question"]}
    out = new_draft(source="Aurora Group assistant", increment=True)
    return apply_request(out["draft_id"], text=text, parsed=reading)


def quote(product, deliver_by):
    from . import portal_intake as intake

    rule = rules()[0]
    calls = []
    api = ValioAPI(fresh=True)
    options, delivery = intake.quote_options(product, deliver_by, {"free_from": rule["allergens"], "strict_may_contain": True}, api, calls)
    return {"options": options, "delivery": delivery, "calls": len(api.audit)}


def history():
    # Account history is explicitly imported through the real order flow by the
    # maintenance script. Never generate past orders on a user's first page load.
    cached, _ = Store().get("history")
    return cached or {"orders": []}
