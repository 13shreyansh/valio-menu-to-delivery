"""Public remote MCP door, confined to the synthetic Hotel Aurora account.
No caller-supplied approval or customer identifier is accepted.
"""

from mcp.server.mcpserver import MCPServer
from . import portal
from .kitchen import KitchenError
from mcp.server.mcpserver.exceptions import ToolError


def checked(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KitchenError as exc:
        raise ToolError(str(exc)) from None


mcp = MCPServer(
    name="valio-aimo-aurora",
    title="Valio Aimo · Hotel Aurora",
    instructions="Order directly from Valio for Hotel Aurora. Find products and check real prices/stock. Prepare an order from dishes, guest counts and date, then place the returned draft_id. Kitchen rules apply on every call. Never claim that goods ship: this account stores confirmations locally because Valio has no order API. Human approvals must be performed by Sanna in the portal. You cannot approve for her.",
)


def compact(o):
    return (
        {
            "review_url": "https://valio-menu-to-delivery.vercel.app/orders/draft-"
            + str(o.get("draft_id", ""))
        }
        | {
            key: o.get(key)
            for key in [
                "draft_id",
                "order_number",
                "status",
                "total",
                "budget",
                "pending",
                "can_place",
                "request",
                "confirmation",
            ]
        }
        | {
            "checks": [
                {
                    "id": c["id"],
                    "reason": c["text"],
                    "approved": c["approved"],
                    "can_approve": c["can_approve"],
                }
                for c in o.get("checks", [])
            ],
            "deliveries": [
                {
                    "date": d["date"],
                    "subtotal": d["subtotal"],
                    "cutoff": d["cutoff"],
                    "products": [
                        {
                            "product_id": r["product_id"],
                            "name": r["name"],
                            "quantity": r["units"],
                            "pack": r["pack"],
                            "unit": r["unit"],
                            "unit_price": r["unit_price"],
                            "total": r["total"],
                        }
                        for r in d["rows"]
                    ],
                }
                for d in o.get("deliveries", [])
            ],
        }
    )


@mcp.tool(
    description="Find real Valio products, with account-specific prices and current stock. Scoped to Hotel Aurora. Products marked allowed=false cannot be ordered under this kitchen’s rules."
)
def find_products(query: str) -> dict:
    return checked(portal.search, query)


@mcp.tool(
    description="Check Valio price, stock, available date and cut-off for up to 50 product IDs. This does not order anything. Scoped to Hotel Aurora customer HC-1001."
)
def check_stock_and_prices(
    product_ids: list[str], delivery_date: str = "2026-11-18"
) -> dict:
    from .valio_api import ValioAPI
    from .kitchen import KitchenError

    if not 1 <= len(product_ids) <= 50 or delivery_date not in portal.f.DELIVERIES:
        raise KitchenError("Choose up to 50 products and a kitchen delivery day.")
    a = ValioAPI(fresh=True)
    return {
        "prices": a.price(delivery_date, product_ids),
        "stock": a.availability(delivery_date, product_ids),
        "calls": a.audit,
    }


@mcp.tool(
    description="Prepare an order from dishes, guests and a day. Example: breakfast for 40 for Wednesday. Uses kitchen recipes, real Valio customer prices, stock and cut-offs, and the same weekly limit, allergens, swap and bigger-change rules as the portal. Returns draft_id. No approvals can be bypassed."
)
def prepare_order(request: str) -> dict:
    o = checked(portal.prepare_assistant, request)
    return o if o.get("question") else compact(o)


@mcp.tool(
    description="Place the draft returned by prepare_order. Re-checks prices, supply and all current kitchen rules. Orders needing an OK must be reviewed by the chef in the portal. Stores the confirmation in Hotel Aurora Orders, Recent orders and the account bell. Valio has no shipping/order API, so this is a demo-account confirmation."
)
def place_order(draft_id: str) -> dict:
    o = checked(portal.place, draft_id, assistant=True)
    return compact(o) | {
        "message": f"Order {o['order_number']} placed by Aurora Group assistant · Within your rules",
        "notice": "Demo account: no real order was placed.",
    }
