"""One ordering engine and account ledger for the portal and remote MCP clients."""

import httpx

import copy, datetime as dt, math, time, uuid
from types import SimpleNamespace
from . import kitchen as k, portal_fixtures as f
from .account_store import Store, Conflict
from .kitchen_intake import understand
from .guardrails import product_violations
from .valio_api import ValioAPI
from .catalog import load

now = lambda: dt.datetime.now(k.TZ).isoformat()


def rules():
    value, version = Store().get("rules")
    return value or copy.deepcopy(f.RULES), version


def save_rules(value):
    current, etag = rules()
    for key in ["weekly_limit", "growth_limit"]:
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
        allowed = {
            "nuts",
            "peanuts",
            "milk",
            "egg",
            "fish",
            "gluten",
            "sesame",
            "soy",
            "celery",
            "mustard",
            "crustaceans",
            "molluscs",
            "sulphites",
            "lupin",
        }
        if not isinstance(value["allergens"], list) or any(
            a not in allowed for a in value["allergens"]
        ):
            raise k.KitchenError("Choose an allergen from the list.")
        current["allergens"] = list(dict.fromkeys(value["allergens"]))
    current.update(changed_at=now(), changed_by="Sanna", version=current["version"] + 1)
    Store().put("rules", current, etag)
    return current


def context(rule):
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
    data["KITCHEN"]["budget"] = rule["weekly_limit"]
    data["KITCHEN"]["same_allergens"] = rule["same_allergens"]
    data["KITCHEN"]["policy"] = {
        "free_from": rule["allergens"],
        "strict_may_contain": True,
    }
    return SimpleNamespace(**data)


def build(state, fresh=False, progress=None):
    rule, _ = rules()
    state["budget"] = rule["weekly_limit"]
    out = k.build(state, fresh=fresh, context=context(rule), progress=progress)
    checks = out["checks"]
    if not any(r["units"] > 0 for r in out["rows"]):
        checks.append(
            {
                "id": "empty",
                "kind": "gap",
                "text": "There is nothing to order. Add a meal or a product first.",
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
    if out["total"] > rule["weekly_limit"] and rule["over_limit"] == "block":
        for c in checks:
            if c["kind"] == "budget":
                c["can_approve"] = False
                c["text"] = (
                    "Your weekly limit does not allow this order. Change the order or your rule."
                )
    growth = out["total"] - state.get("baseline_total", out["total"])
    if growth > rule["growth_limit"] and not any(c["kind"] == "budget" for c in checks):
        checks.append(
            {
                "id": "growth",
                "kind": "budget",
                "text": f"This order grew by €{growth:.2f}. Your rule asks for an OK above €{rule['growth_limit']:.2f}.",
                "can_approve": True,
                "row_ids": [r["id"] for r in out["rows"]],
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
    rows = {r["id"]: r for r in out["rows"]}
    for c in checks:
        c["fingerprint"] = k.digest(
            [
                rule,
                c["id"],
                [
                    [
                        rid,
                        rows[rid]["product_id"],
                        rows[rid]["units"],
                        rows[rid]["unit_price"],
                    ]
                    for rid in c["row_ids"]
                ],
            ]
        )
        ack = state["approvals"].get(c["id"])
        c["approved"] = bool(
            c["can_approve"] and ack and ack["fingerprint"] == c["fingerprint"]
        )
        c["approved_at"] = ack.get("at") if c["approved"] else None
        c["reopened"] = bool(ack and not c["approved"])
    out.update(
        pending=sum(not c["approved"] for c in checks),
        can_place=all(c["approved"] for c in checks),
        rules=rule,
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


def new_draft(services=None, source="Sanna Virtanen"):
    state = k.initial_state()
    state.update(
        id=uuid.uuid4().hex, status="draft", source=source, request="", request_at=now()
    )
    if services is not None:
        state["services_override"] = services
    out = build(state)
    state["baseline_total"] = out["total"] if services is None else 0
    state["baseline_rows"] = copy.deepcopy(out["rows"])
    Store().put("drafts/" + state["id"], state)
    out["draft_id"] = state["id"]
    index_draft(state, out)
    return out


def draft(draft_id):
    if (
        not isinstance(draft_id, str)
        or len(draft_id) != 32
        or not all(c in "0123456789abcdef" for c in draft_id)
    ):
        raise k.KitchenError("Choose an order from your account.")
    state, version = Store().get("drafts/" + draft_id)
    if not state:
        raise k.KitchenError("This order could not be found.")
    return state, version


def get_draft(draft_id):
    state, _ = draft(draft_id)
    committed = committed_order(draft_id)
    if committed:
        return committed
    if state["status"] == "placed":
        return state["placed_order"]
    return build(state)


def change(draft_id, action, value=None):
    state, version = draft(draft_id)
    if state["status"] != "draft" or committed_order(draft_id):
        raise k.KitchenError(
            "This order is already placed. Start another order to change it."
        )
    out = build(state)
    if action == "approve":
        c = next((c for c in out["checks"] if c["id"] == value), None)
        if not c or not c["can_approve"]:
            raise k.KitchenError(
                "Change the menu or quantity before placing this order."
            )
        if value == "swap":
            state["keep_original"] = False
        state["approvals"][value] = {
            "fingerprint": c["fingerprint"],
            "at": dt.datetime.now(k.TZ).strftime("%H:%M"),
        }
    elif action == "unapprove":
        state["approvals"].pop(value, None)
    elif action == "quantity":
        row = next((r for r in out["rows"] if r["id"] == value.get("id")), None)
        n = value.get("units")
        if not row or type(n) is not int or not 0 <= n <= 9999:
            raise k.KitchenError("Use a whole number of packs from 0 to 9999.")
        state["overrides"][row["id"]] = n
    elif action == "small-cream":
        state["small_cream"] = True
    elif action == "keep-original":
        # There is no safe path to order unavailable fish. Keeping it keeps the order blocked.
        state["keep_original"] = True
    elif action == "restore":
        state["overrides"].pop(value, None)
    elif action == "add":
        pid = str(value)
        existing = next(
            (
                r
                for r in out["rows"]
                if r["product_id"] == pid and r["delivery"] == f.DELIVERIES[-1]
            ),
            None,
        )
        if existing:
            state["overrides"][existing["id"]] = existing["units"] + 1
        else:
            extra = next((e for e in state["extra"] if e["product_id"] == pid), None)
            if extra:
                extra["units"] += 1
            else:
                state["extra"].append({"product_id": pid, "units": 1})
    else:
        raise k.KitchenError("That change is not supported.")
    state["events"].append(
        {"action": action, "value": value, "at": now(), "by": "Sanna"}
    )
    result = build(state)
    Store().put("drafts/" + draft_id, state, version)
    index_draft(state, result)
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
    state, version = draft(draft_id)
    if state["status"] != "draft" or committed_order(draft_id):
        raise k.KitchenError("This order has already been placed.")
    start = time.time()
    if parsed:
        reading = parsed
    elif source == "text":
        from .portal_intake import understand_order

        general = understand_order(text)
        if general.get("question"):
            return {
                "reading": general,
                "question": general["question"],
                "draft_id": draft_id,
            }
        reading = {
            "status": "readable",
            "transcript": text,
            "covers": general["dishes"][0]["covers"] if general["dishes"] else 0,
            "action": general.get("action", "add"),
            "dishes": general["dishes"],
            "date": general["date"],
            "event": general.get("event", "Kitchen change"),
            "source": source,
        }
        state["calls"].append(general["call"])
    else:
        reading = understand(text=text, media=media, source=source)
        state["calls"].append(
            {
                "source": "Gemini",
                "method": "POST",
                "purpose": source + " understanding",
                "status": 200,
                "at": start,
                "duration_ms": round((time.time() - start) * 1000),
                "request": {"media_type": media.get("mime") if media else None},
                "response": reading,
            }
        )
    if progress:
        progress("read", reading)
    if reading["status"] != "readable":
        return {
            "reading": reading,
            "question": reading.get("reason") or "How many guests and which dishes?",
            "draft_id": draft_id,
        }
    before = build(state)
    state["previous_rows"] = copy.deepcopy(before["rows"])
    state["previous_total"] = before["total"]
    state["request"] = reading["transcript"]
    state["request_at"] = now()
    state["reading"] = reading
    if reading.get("action") == "close":
        rule, _ = rules()
        state["services_override"] = [
            service
            for service in k.services_for(state, context(rule))
            if service["date"] != reading["date"]
        ]
        state["wedding"] = None
        state["menu_events"] = []
    else:
        event = {
            "date": reading.get("date", "2026-11-21"),
            "event": reading.get("event", "Wedding"),
            "covers": reading["covers"],
            "dishes": reading["dishes"],
            "transcript": reading["transcript"],
            "from_photo": source == "photo",
        }
        events = state.setdefault(
            "menu_events",
            [copy.deepcopy(state["wedding"])] if state.get("wedding") else [],
        )
        if (
            source == "photo"
            and "wedding" in event["event"].casefold()
            and not replace_event_id
        ):
            previous_wedding = next(
                (
                    item
                    for item in events
                    if item["date"] == event["date"]
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
                    if e["date"] == event["date"]
                    and e.get("event", "Wedding").casefold()
                    == event["event"].casefold()
                ),
                None,
            )
        )
        event["id"] = target.get("id", uuid.uuid4().hex) if target else uuid.uuid4().hex
        if target:
            events[events.index(target)] = event
        else:
            events.append(event)
        state["wedding"] = event
        reading["event_id"] = event["id"]
    state["overrides"] = {}
    state["keep_original"] = False
    out = build(state, progress=progress)
    if progress:
        progress("allergens", out)
        progress("budget", out)
    Store().put("drafts/" + draft_id, state, version)
    index_draft(state, out)
    return out


def ledger():
    doc, version = Store().get("ledger")
    return doc or {"orders": [], "events": []}, version


def index_draft(state, out):
    entry = {
        "draft_id": state["id"],
        "order_number": "Week 47",
        "placed_by": state["source"],
        "placed_at": state["request_at"],
        "deliveries": [{"date": d["date"]} for d in out["deliveries"]],
        "total": out["total"],
        "products": sum(r["units"] > 0 for r in out["rows"]),
        "status": "Draft",
        "request": state.get("request", ""),
    }
    for attempt in range(4):
        book, etag = ledger()
        if any(o["draft_id"] == state["id"] for o in book["orders"]):
            return
        entries = book.setdefault("drafts", [])
        existing = next(
            (i for i, d in enumerate(entries) if d["draft_id"] == state["id"]), None
        )
        if existing is None:
            entries.insert(0, entry)
        else:
            entries[existing] = entry
        try:
            Store().put("ledger", book, etag)
            return
        except Conflict:
            if attempt == 3:
                raise


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
    committed = committed_order(draft_id)
    if committed:
        return committed
    if state["status"] == "placed":
        return state["placed_order"]
    out = build(state, fresh=True)
    if state.get("keep_original") or not out["can_place"]:
        raise k.KitchenError(
            "This order needs a chef to review it before it can be placed."
        )
    oid = "AU-" + draft_id[:8].upper()
    by = "Aurora Group assistant" if assistant else "Sanna Virtanen"
    out.update(
        status="placed",
        order_number=oid,
        placed_by=by,
        placed_at=now(),
        week=47,
        within_rules=True,
        confirmation={"order_number": oid, "at": now(), "demo": True},
    )
    # The immutable snapshot exists before its pointer can be committed to the ledger.
    # The successful conditional ledger write is the only commitment point.
    snapshot_key = "orders/" + draft_id + "/" + uuid.uuid4().hex
    Store().put(snapshot_key, out)
    for attempt in range(4):
        book, etag = ledger()
        committed = committed_order(draft_id, book)
        if committed:
            return committed
        book["orders"].insert(
            0,
            {
                "order_number": oid,
                "draft_id": draft_id,
                "snapshot_key": snapshot_key,
                "placed_by": by,
                "placed_at": out["placed_at"],
                "total": out["total"],
                "products": sum(r["units"] > 0 for r in out["rows"]),
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
                "within_rules": True,
            },
        )
        for item in book.get("drafts", []):
            if item["draft_id"] == draft_id:
                item["status"] = "Placed"
        book["events"].insert(
            0,
            {
                "id": oid,
                "by": by,
                "text": f"{by} placed order {oid}",
                "total": out["total"],
                "at": out["placed_at"],
                "note": "Within your rules",
            },
        )
        try:
            Store().put("ledger", book, etag)
            break
        except Conflict:
            if attempt == 3:
                raise
    # This draft is only a convenience copy. A failed write cannot change commitment.
    state.update(status="placed", placed_order=out)
    try:
        Store().put("drafts/" + draft_id, state, version)
    except (Conflict, k.KitchenError, httpx.HTTPError):
        pass
    return out


def account():
    rule, _ = rules()
    book, _ = ledger()
    return {
        "name": f.KITCHEN["name"],
        "team": f.TEAM,
        "rules": rule,
        "orders": book["orders"] + history()["orders"],
        "drafts": [d for d in book.get("drafts", []) if d["status"] == "Draft"],
        "events": book["events"],
        "bookings": f.KITCHEN["bookings"],
        "recipes": f.RECIPES,
        "stock": f.STOCK,
        "menu": f.BASE_SERVICES,
        "mcp_url": "https://valio-menu-to-delivery.vercel.app/mcp/",
    }


def search(query):
    rule, _ = rules()
    cat = load()
    ps = [p for p, _ in cat.search(query or "Valio milk", k=20)]
    if query and cat.get(query):
        ps = [cat.get(query)]
    api = ValioAPI()
    ids = [p["id"] for p in ps]
    date = f.DELIVERIES[-1]
    prices = api.price(date, ids)
    stock = api.availability(date, ids)
    out = []
    for p in ps:
        pr = prices.get(p["id"], {})
        av = stock.get(p["id"], {})
        if pr.get("unit_price") is None:
            continue
        out.append(
            {
                **p,
                **pr,
                "availability": av,
                "allowed": not product_violations(
                    p,
                    policy={"free_from": rule["allergens"], "strict_may_contain": True},
                )
                and av.get("orderable")
                and not k.cutoff_passed(av.get("closing_time")),
            }
        )
    return {"products": out, "calls": api.audit}


def prepare_assistant(text):
    """Gemini reads a normal request. The same deterministic recipes and rules do the rest."""
    from .portal_intake import understand_order

    reading = understand_order(text)
    if reading.get("question"):
        return reading
    date = reading["date"]
    services = [
        {"date": date, "recipe": d["recipe"], "covers": d["covers"]}
        for d in reading["dishes"]
    ]
    out = new_draft(services=services, source="Aurora Group assistant")
    state, ver = draft(out["draft_id"])
    state.update(request=text, reading=reading, request_at=now())
    state["calls"].append(reading["call"])
    out = build(state)
    Store().put("drafts/" + state["id"], state, ver)
    index_draft(state, out)
    return out


def history():
    cached, etag = Store().get("history")
    if cached:
        return cached
    state = k.initial_state()
    state["budget"] = 1500
    out = build(state)
    api = ValioAPI()
    allids = list(dict.fromkeys(r["product_id"] for r in out["rows"]))
    orders = []
    for record in f.HISTORY:
        prices = api.price(record["date"], allids)
        lines = []
        for r in out["rows"]:
            pr = prices.get(r["product_id"], {})
            if pr.get("unit_price") is None:
                raise k.KitchenError("Could not price the account history from Valio.")
            n = max(1, math.ceil(r["units"] * record["factor"]))
            lines.append(
                {
                    **r,
                    "units": n,
                    "unit_price": pr["unit_price"],
                    "total": round(n * pr["unit_price"], 2),
                }
            )
        orders.append(
            {
                "order_number": record["id"],
                "placed_by": record["by"],
                "placed_at": record["date"] + "T15:00:00+02:00",
                "total": round(sum(r["total"] for r in lines), 2),
                "products": len(lines),
                "deliveries": [
                    {
                        "date": record["date"],
                        "rows": lines,
                        "subtotal": round(sum(r["total"] for r in lines), 2),
                        "cutoff": None,
                    }
                ],
                "status": "Delivered",
                "historical": True,
                "price_checked_at": now(),
                "rows": lines,
            }
        )
    result = {
        "orders": orders,
        "calls": api.audit,
        "note": "Authored Hotel Aurora past quantities, valued with real Valio customer prices. These are sample account records, not supplier invoices.",
    }
    try:
        Store().put("history", result, etag)
    except Conflict:
        result, _ = Store().get("history")
    return result
