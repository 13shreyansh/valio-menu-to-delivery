"""Outside HTTPS MCP client. No browser cookies, account token or approval override."""

import json, sys
import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://valio-menu-to-delivery.vercel.app"
c = httpx.Client(
    base_url=BASE,
    timeout=240,
    follow_redirects=True,
    headers={
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    },
)


def rpc(method, params=None):
    r = c.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )
    r.raise_for_status()
    v = r.json()
    if "error" in v:
        raise RuntimeError(v["error"])
    return v.get("result", {})


def call(name, args):
    result = rpc("tools/call", {"name": name, "arguments": args})
    if result.get("isError"):
        raise RuntimeError(result)
    if result.get("structuredContent"):
        return result["structuredContent"]
    return json.loads(next(c["text"] for c in result["content"] if c["type"] == "text"))


init = rpc(
    "initialize",
    {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "Aurora Group outside client", "version": "1.0"},
    },
)
tools = rpc("tools/list")["tools"]
assert {"find_products", "check_stock_and_prices", "prepare_order", "place_order"} <= {
    t["name"] for t in tools
}
q = call(
    "check_stock_and_prices", {"product_ids": ["463380"], "delivery_date": "2026-11-18"}
)
assert q["prices"]["463380"]["unit_price"] > 0
p = call(
    "prepare_order",
    {"request": "Order breakfast for 40 for Hotel Aurora’s Wednesday conference."},
)
assert p["can_place"], p
placed = call("place_order", {"draft_id": p["draft_id"]})
assert placed["order_number"] and placed["status"] == "placed"
assert "Aurora Group assistant" in placed["message"]
print(
    json.dumps(
        {
            "protocol": init["protocolVersion"],
            "tools": len(tools),
            "draft_id": p["draft_id"],
            "order_number": placed["order_number"],
            "total_measured": placed["total"],
            "message": placed["message"],
        }
    )
)
