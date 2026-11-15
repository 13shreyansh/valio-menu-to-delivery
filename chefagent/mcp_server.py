"""Valio Aimo's door for a buyer's own purchasing agent (MCP, Streamable HTTP).

Each call is tied to one buyer account by its bearer token. The agent can look
up, quote and order within that account's rules. It can never approve for a person.
"""

import datetime as dt
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from . import portal
from .kitchen import KitchenError, TZ, cutoff_passed
from .portal_intake import WEEK, nice_day


def checked(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KitchenError as exc:
        raise ToolError(str(exc)) from None


mcp = MCPServer(
    name="valio-aimo",
    title="Valio Aimo ordering",
    instructions=(
        "Order from Valio Aimo for the buyer account this token belongs to. "
        "Typical flow for a product request such as '1,000 litres of lactose-free milk by Monday': "
        "call order_products (it finds matching products, compares live price and stock, picks the best offer and "
        "places the order if the account's rules allow, or returns needs_approval with a review link for a person). "
        "Use quote_products to compare offers without ordering, find_products to browse, and prepare_order for "
        "dishes and guest counts. Orders are for delivery week 47 (16 to 22 November 2026); deliveries arrive Monday, "
        "Wednesday and Friday. Prices are fixed customer prices excluding VAT. The account's limits, allergen rules and "
        "approval rules apply to every call and cannot be changed or approved through this interface. "
        "This is Valio's Junction 2026 mock: placed orders are recorded on the account and nothing ships."
    ),
)


class Offer(BaseModel):
    product_id: str
    name: str
    rank: Optional[str] = Field(None, description="Best, Better or Good among offers that meet the request")
    status: Literal["ok", "partial", "cutoff", "late"] = Field(description="ok = can deliver the full quantity in time")
    note: Optional[str] = None
    pack: float = Field(description="Content of one sales unit")
    pack_unit: str
    unit_price: float = Field(description="EUR per sales unit, excluding VAT")
    price_per_unit: float = Field(description="EUR per litre or kilogram, excluding VAT")
    packs: int = Field(description="Sales units needed for the requested quantity")
    total: float = Field(description="EUR for those sales units, excluding VAT")
    available_packs: int
    available_date: Optional[str] = None
    cutoff: Optional[str] = Field(None, description="Order-by time for this delivery")
    reliability: Optional[float] = Field(None, description="Share of past deliveries on time and complete, 0 to 1")
    co2_per_kg: Optional[float] = None
    labels: list[str] = []
    contains: list[str] = Field([], description="Declared allergens (GS1 allergen codes mapped to plain names)")


class Quote(BaseModel):
    request: str
    quantity: float
    unit: str
    deliver_by: str
    delivery_day: str
    offers: list[Offer]
    checked_at: str
    source: str = "Live Valio Aimo price and availability API, customer HC-1001"


class Line(BaseModel):
    product_id: str
    name: str
    quantity: int = Field(description="Sales units")
    pack: float
    unit: str
    unit_price: float
    total: float
    why: Optional[str] = None


class Delivery(BaseModel):
    date: str
    subtotal: float
    order_by: Optional[str] = None
    products: list[Line]


class Approval(BaseModel):
    id: str
    reason: str
    detail: str
    approved: bool
    a_person_can_approve: bool


class Order(BaseModel):
    status: Literal["placed", "needs_approval", "ready_to_place", "question"]
    message: str
    draft_id: Optional[str] = None
    order_number: Optional[str] = None
    review_url: Optional[str] = Field(None, description="Where the head chef reviews and approves")
    total: Optional[float] = Field(None, description="EUR excluding VAT")
    weekly_limit: Optional[float] = None
    already_placed_this_week: Optional[float] = None
    approvals: list[Approval] = []
    deliveries: list[Delivery] = []
    notes: list[str] = []
    question: Optional[str] = None


def order_view(o, status=None, message=None):
    if o.get("question"):
        return Order(status="question", message=o["question"], question=o["question"])
    placed = o.get("status") == "placed"
    status = status or ("placed" if placed else "ready_to_place" if o["can_place"] else "needs_approval")
    open_checks = [c for c in o.get("checks", []) if not c["approved"]]
    if not message:
        message = (
            f"Order {o.get('order_number')} is recorded on the account. {o.get('rule_note', '')}. Demo account: Valio's mock has no order API, so nothing ships."
            if placed
            else "Within the account's rules. Call place_order with this draft_id to place it."
            if status == "ready_to_place"
            else "A person must approve before this can be placed: " + "; ".join(portal.check_label(c) for c in open_checks[:4]) + ". Send the head chef the review_url."
        )
    return Order(
        status=status,
        message=message,
        draft_id=o.get("draft_id"),
        order_number=o.get("order_number"),
        review_url=portal.SITE + "/orders/" + (o["order_number"] if placed else "draft-" + str(o.get("draft_id"))),
        total=o.get("total"),
        weekly_limit=o.get("budget"),
        already_placed_this_week=o.get("week_placed"),
        approvals=[
            Approval(id=c["id"], reason=portal.check_label(c), detail=c["text"], approved=c["approved"], a_person_can_approve=c["can_approve"])
            for c in o.get("checks", [])
        ],
        deliveries=[
            Delivery(
                date=d["date"],
                subtotal=d["subtotal"],
                order_by=d.get("cutoff"),
                products=[
                    Line(product_id=r["product_id"], name=r["name"], quantity=r["units"], pack=r["pack"], unit=r["unit"], unit_price=r["unit_price"], total=r["total"], why=r.get("reason"))
                    for r in d["rows"]
                    if r["units"] > 0
                ],
            )
            for d in o.get("deliveries", [])
        ],
        notes=o.get("notes") or [],
    )


def day(value):
    """Accepts YYYY-MM-DD or a weekday name in week 47."""
    text = str(value or "").strip().lower()
    names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, name in enumerate(names):
        if text.startswith(name[:3]):
            return WEEK[i]
    if text in WEEK:
        return text
    raise KitchenError("deliver_by must be a day in week 47: 2026-11-16 to 2026-11-22, or a weekday name. Deliveries arrive Monday, Wednesday and Friday.")


def need(query, quantity, unit, product_id=None, lactose_free=False, gluten_free=False, vegan=False, organic=False):
    unit = {"litre": "l", "litres": "l", "liter": "l", "liters": "l", "l": "l", "kg": "kg", "kilogram": "kg", "kilograms": "kg"}.get(str(unit).lower(), "pcs")
    if not isinstance(quantity, (int, float)) or not 0 < quantity <= 100000:
        raise KitchenError("quantity must be above 0 and at most 100,000.")
    q = str(query or "")
    return {
        "name": q[:60] or "product " + str(product_id), "search_fi": q[:60], "search_en": q[:60], "quantity": float(quantity), "unit": unit,
        "lactose_free": lactose_free or "lactose" in q.lower() or "laktoositon" in q.lower(), "gluten_free": gluten_free, "vegan": vegan, "organic": organic,
        "product_id": str(product_id) if product_id else None,
    }


@mcp.tool(
    title="Find products",
    description="Search Valio Aimo's catalogue. Returns products with the account's fixed price, live stock, delivery day, order-by time, allergens, labels and CO2 per kg. allowed=false products cannot be ordered under this account's rules; reason says why. Claims such as 'lactose-free' or 'gluten-free' in the query filter the results.",
)
def find_products(query: str) -> dict[str, Any]:
    out = checked(portal.search, query)
    return {"products": out["products"], "checked_at": portal.now()}


@mcp.tool(
    title="Check stock and prices",
    description="Live price, stock, available date and order-by time for up to 50 product IDs on a delivery day (2026-11-16, 2026-11-18 or 2026-11-20). Does not order anything.",
)
def check_stock_and_prices(product_ids: list[str], delivery_date: str = "2026-11-18") -> dict[str, Any]:
    from .valio_api import ValioAPI

    if not 1 <= len(product_ids) <= 50 or delivery_date not in portal.f.DELIVERIES:
        raise ToolError("Choose up to 50 products and a delivery day: 2026-11-16, 2026-11-18 or 2026-11-20.")
    a = ValioAPI(fresh=True)
    return {
        "prices": a.price(delivery_date, product_ids),
        "stock": a.availability(delivery_date, product_ids),
        "checked_at": portal.now(),
    }


@mcp.tool(
    title="Quote products",
    description="Compare real offers for a product need without ordering, e.g. query='lactose-free milk', quantity=1000, unit='l', deliver_by='Monday'. Returns every matching product ranked by price per litre or kilogram among those that can deliver the full quantity in time (rank Best, Better, Good), with pack maths, live stock, order-by time, delivery record and labels. Products that are late, past their order-by time or short of stock are listed with the reason.",
)
def quote_products(query: str, quantity: float, unit: str = "l", deliver_by: str = "Monday", lactose_free: bool = False, gluten_free: bool = False, vegan: bool = False, organic: bool = False, product_id: Optional[str] = None) -> Quote:
    try:
        date = day(deliver_by)
        n = need(query, quantity, unit, product_id, lactose_free, gluten_free, vegan, organic)
        out = portal.quote(n, date)
    except KitchenError as exc:
        raise ToolError(str(exc)) from None
    return Quote(request=n["name"], quantity=n["quantity"], unit=n["unit"], deliver_by=date, delivery_day=out["delivery"], offers=[Offer(**{key: v for key, v in o.items() if key in Offer.model_fields}) for o in out["options"]], checked_at=portal.now())


class Item(BaseModel):
    query: Optional[str] = Field(None, description="What to buy in words, e.g. 'lactose-free milk'. Use this or product_id.")
    product_id: Optional[str] = Field(None, description="Exact Valio product code, if known")
    quantity: float = Field(description="Amount in the given unit")
    unit: str = Field("l", description="'l', 'kg' or 'pcs' (sales units)")
    lactose_free: bool = False
    gluten_free: bool = False
    vegan: bool = False
    organic: bool = False


@mcp.tool(
    title="Order products",
    description="Order products by description or product code, quantity and delivery deadline. For each item Valio compares the matching products on live price and stock, picks the best offer that can arrive in time (splitting across products if stock is partial) and checks the account's limits and rules. If everything is within the agent's authority and place_if_allowed is true, the order is placed and status is 'placed'. Otherwise status is 'needs_approval' with the reasons and a review_url for the head chef. Nothing is ever approved on a person's behalf.",
)
def order_products(items: list[Item], deliver_by: str = "Monday", place_if_allowed: bool = True, note: str = "") -> Order:
    try:
        date = day(deliver_by)
        if not 1 <= len(items) <= 6:
            raise KitchenError("Send 1 to 6 items.")
        products = [need(i.query, i.quantity, i.unit, i.product_id, i.lactose_free, i.gluten_free, i.vegan, i.organic) for i in items]
        text = note.strip()[:300] or "; ".join(f"{p['quantity']:,.0f} {p['unit']} {p['name']}" for p in products) + f" by {nice_day(date)}"
        reading = {"status": "readable", "transcript": text, "source": "assistant", "kind": "products", "event": "Product order", "date": date, "covers": 0, "dishes": [], "products": products, "dietary": [], "assumptions": []}
        o = portal.assistant_request(text, parsed=reading)
        if o.get("can_place") and place_if_allowed:
            o = portal.place(o["draft_id"], assistant=True)
        elif not o.get("can_place"):
            portal.log_event(
                "Aurora Group assistant prepared an order that needs your OK",
                note="Not placed: " + "; ".join(portal.check_label(c) for c in o["checks"] if not c["approved"])[:200],
                by="Aurora Group assistant", total=o["total"], link="/orders/draft-" + o["draft_id"],
            )
    except KitchenError as exc:
        raise ToolError(str(exc)) from None
    return order_view(o)


@mcp.tool(
    title="Prepare an order from dishes",
    description="Prepare an order from a kitchen request in plain words: dishes, guests and a day (e.g. 'Wedding on Saturday, 120 guests: salmon soup, whitefish with potatoes, lemon tart'), or products and amounts. Uses the kitchen's recipes, stock and standing weekly order, real Valio prices, stock and order-by times, and the same rules as the portal. Returns a draft with status ready_to_place or needs_approval. Does not place anything.",
)
def prepare_order(request: str) -> Order:
    o = checked(portal.assistant_request, request)
    if not o.get("question") and not o.get("can_place"):
        checked(
            portal.log_event,
            "Aurora Group assistant prepared an order that needs your OK",
            note="Not placed: " + "; ".join(portal.check_label(c) for c in o["checks"] if not c["approved"])[:200],
            by="Aurora Group assistant", total=o["total"], link="/orders/draft-" + o["draft_id"],
        )
    return order_view(o)


@mcp.tool(
    title="Place a prepared order",
    description="Place a draft returned by prepare_order or order_products. Prices, stock and every account rule are checked again at this moment. If the draft needs a person's approval the call fails with the reasons and the review link, and the refusal is logged on the account. Placed orders appear in the account's Orders and activity log. Demo account: Valio's mock has no order API, so nothing ships.",
)
def place_order(draft_id: str) -> Order:
    return order_view(checked(portal.place, draft_id, assistant=True))


@mcp.tool(
    title="Order status",
    description="Read a draft or placed order by draft_id: status, lines, totals and which approvals are still open.",
)
def order_status(draft_id: str) -> Order:
    return order_view(checked(portal.get_draft, draft_id))
