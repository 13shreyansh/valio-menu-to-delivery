# Valio Aimo: menu to delivery

**Live app:** https://valio-menu-to-delivery.vercel.app · **MCP endpoint:** `https://valio-menu-to-delivery.vercel.app/mcp/`

Built at Junction 2026 for Valio Aimo's *Trusted Trade Agents* challenge.

A hotel head chef pastes next week's menu, or types a request like *"I need 1,000 litres of lactose-free milk by Monday"*. The agent returns one cart, grouped by delivery date and priced at the kitchen's own prices. Allergen rules are enforced, every choice is explained, and the chef approves it with one tap. This is not a chatbot: it is a purchasing workflow inside the webshop, and it is also open to other agents through MCP.

Valio's goal is share of wallet. A kitchen stays with the supplier whose ordering is effortless. Turning a menu into a correct order takes a purchaser an hour across recipes, pack sizes, cut-offs and allergens. Here it takes one paste and one tap.

## The flow (Valio's handout: Request → Lookup → Order → Approval)

| Step | What happens | Where |
|---|---|---|
| **1. Request** | Free text is parsed into services: a menu with dates, covers and diet tags, or a direct request with quantity and arrival date. Dishes expand into recipe components in grams per portion. | `chefagent/intake.py`, `planner.expand` |
| **2. Lookup** | BM25 search over Valio's catalogue (12,643 food items) builds a shortlist. **Products that break the kitchen's allergen or diet rules are removed before the LLM sees them.** The LLM ranks acceptable products. Only the top 8 are priced and availability-checked, never the whole catalogue. Each plan reports its API usage. | `catalog.py`, `guardrails.py`, `planner.candidates/pick` |
| **3. Order** | Deterministic code does the rest. It works out pack size from the price API (unit price ÷ comparison price), rounds to whole packs, checks stock and delivery date, and fixes the price the API quotes. A direct request takes the cheapest viable option. A menu line takes the best recipe fit. Up to 3 options are compared on €/kg, delivery reliability and CO₂/kg. When stock is short it tries Valio's own substitution links, then a recipe-level substitute for a human to approve, and otherwise reports a gap. | `planner.choose/resolve_need` |
| **4. Approval** | A policy engine flags lines and deliveries. Inside policy, the agent places the order. Outside it, the delivery waits for a human. `submit_order` re-checks the mandate **on Valio's side**, so a buyer agent cannot bypass it. Every step is written to a human-readable audit log. | `policy.py`, `service.submit_order` |

Policy rules per kitchen:
- **R1:** spend over the auto-approve limit
- **R2:** substitution (automatic or ask, per kitchen)
- **R3:** may-contain an excluded allergen
- **R4:** pack size not confirmed by the price API
- **R5:** gap

## Open by design

- **MCP server** (streamable HTTP, stateless) at `/mcp/`. Tools:
  - `request_order` (plain-language request → draft order)
  - `plan_menu_order`, `search_products`, `get_product`, `quote`, `find_substitutes`
  - `submit_order`, which re-checks the mandate
- The **HTTP API** mirrors these tools (`/api/plan`, `/api/submit`, `/api/search`, `/api/quote`, `/api/substitutes`, `/api/parse-menu`).
- It is built on **Valio's Junction API** (price, availability, products, delivery reliability, carbon). The order endpoint is a mock, because the API has none.

## How we test it

See `eval/README.md` and `eval/METRICS_LOG.md`. There are two evals, both graded by code:

1. **Menu → cart.** 39 hand-written recipe cards and 124 gold ingredient rules, split 10 dev / 6 held-out cases. A dish is *cookable* if every essential component is bought in at least 80% of the gold quantity, is deliverable by the service date, and breaks no allergen rule. Allergen violations are re-derived by an independent scorer.
2. **Request → commitment → approval.** 13 free-text buyer requests, balanced between cases where the agent should act alone (auto) and cases where it must stop (escalate or refuse). They include stock-outs, late deliveries and a nut request to a nut-free kitchen. We report **pass^k**, meaning all k fresh runs pass, not just pass@1.

| | Floor (keyword top-1, no guardrails) | Agent |
|---|---|---|
| Dishes cookable (dev) | 8% | 70% |
| Dishes cookable (held-out, 14 unseen recipes, run once on frozen v3) | | 65% |
| Allergen/diet violations | 16 | **0** |
| Requests handled correctly, every one of 3 fresh runs (pass^3) | | **13/13** |
| False auto-approvals | | **0** |

What still fails: a dried herb replaces a fresh one at the same weight, small needs can open large frozen packs, and a few picks where the gold rules and the agent disagree. Those go to a chef via `eval/spot_checks.csv`.

## Run it

```bash
pip install -r requirements.txt
export VALIO_API_KEY=...   # Junction portal key
export GEMINI_API_KEY=...
uvicorn api.index:app --port 8000      # downloads + indexes the catalogue on first start (~6 s)
python -m eval.run --split dev --name mytry
python -m eval.requests_eval --name mytry --k 3
```

Valio's product data is for Junction 2026 only, so it is **not** in this repo. The app downloads it from Valio's API at start-up.

## Path to production

- **Swap the mock order endpoint** for the webshop's order API. `submit_order` already has the shape: delivery, customer, approver, and a mandate re-check.
- **Kitchen policies** come from the customer account: limits, allergen rules, substitution permissions.
- **Recipes:** use the kitchen's own recipe cards where they exist. The LLM expansion is the fallback, and every quantity it produces is visible and editable.
- **The audit log** becomes the order history: who decided what, under which rule.
- **Eval in CI:** the two code-graded evals run on every change, and the held-out split runs once per release.

## Assumptions

- Delivery is the day before service, skipping Sunday. A direct request uses the date the buyer asked for.
- 1 L ≈ 1 kg for quantity maths.
- Stock-outs in the eval are a seeded overlay on Valio's mock availability, so runs can be repeated.

MIT licensed. Built by Shreyansh (team "The CS Guy") at Junction 2026.
