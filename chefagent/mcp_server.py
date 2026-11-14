"""MCP server exposing Valio Aimo product intelligence and ordering to any agent.

  stdio : python -m chefagent.mcp_server
  http  : mounted at /mcp by api/index.py (streamable HTTP)
"""
from mcp.server.mcpserver import MCPServer

from . import service

mcp = MCPServer(
    name="valio-aimo-kitchen",
    title="Valio Aimo kitchen ordering",
    instructions=(
        "Tools for professional kitchens buying from Valio Aimo. Prices and stock are customer-specific: always pass "
        "the customer id. Search the static catalogue first, quote only a shortlist. Orders are checked against the "
        "kitchen's mandate on Valio's side: allergen/diet rules, spend limit and substitutions. submit_order returns "
        "pending_approval when a human must tap approve."),
)


@mcp.tool(description="Search Valio Aimo's catalogue. diet tags: vegan, vegetarian, gluten-free, milk-free. Products that break the kitchen's allergen rules are listed under 'excluded' with the reason.")
def search_products(query: str, diet: list[str] | None = None, customer: str = "HC-1001", limit: int = 10) -> dict:
    return service.search_products(query, diet, customer, limit)


@mcp.tool(description="Full product card: allergens (contains / may contain), claims, labels, pack size, origin, delivery reliability, carbon footprint per kg, Valio substitution links.")
def get_product(product_id: str) -> dict:
    return service.get_product(product_id)


@mcp.tool(description="Customer-specific price and availability for up to 50 products on a delivery date (YYYY-MM-DD). Returns pack size in kg/L so quantities can be computed.")
def quote(product_ids: list[str], delivery_date: str, customer: str = "HC-1001") -> dict:
    return service.quote(product_ids, delivery_date, customer)


@mcp.tool(description="Substitutes for a product that cannot be delivered: Valio's own substitution links first, then close same-category items, filtered by the kitchen's rules, with availability on the date.")
def find_substitutes(product_id: str, delivery_date: str, diet: list[str] | None = None, customer: str = "HC-1001") -> dict:
    return service.find_substitutes(product_id, delivery_date, diet, customer)


@mcp.tool(description="Turn a menu into a draft order. services = [{date: 'YYYY-MM-DD' (service day), meal, items: [{text: menu line as the chef wrote it, covers: int, diet: [tags]}]}]. Returns deliveries (lines grouped by delivery date with per-dish allocations), gaps, approval flags and an audit trail. Places nothing.")
def plan_menu_order(services: list[dict], customer: str = "HC-1001") -> dict:
    return service.plan_menu_order(services, customer)


@mcp.tool(description="Place one delivery of a draft order. Valio re-checks the mandate; returns placed, pending_approval (pass approved_by after a human taps approve) or rejected.")
def submit_order(delivery: dict, customer: str = "HC-1001", approved_by: str | None = None) -> dict:
    return service.submit_order(delivery, customer, approved_by)


if __name__ == "__main__":
    mcp.run("stdio")
