# Demo video script (2:00 max)

Record on https://valio-menu-to-delivery.vercel.app at 1440 px wide. Plan the menu sample once before recording so its lookups are warm. Cut the waiting time in editing, and show a "+40 s" caption where you cut.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:12 | Landing page | "A hotel kitchen buys from Valio every day. Turning next week's menu into an order means recipes, pack sizes, allergens, cut-offs and sign-offs. It takes a purchaser an hour. If it took one tap, they'd buy more of it from Valio. That's the business case." |
| 0:12–0:30 | Quick request: type Valio's own example, "I need 1,000 litres of lactose-free milk by Monday", then click **Find, price and order it**. The flow bar runs Request → Lookup → Order → Approval. | "This is Valio's example from the brief. The agent reads it, then searches the catalogue locally. It drops 33 milks this kitchen can't serve, and asks Valio's API to price only 8 of 12,643 products." |
| 0:30–0:45 | Open **Why this product** on the line. | "It compares three options on price per litre, delivery reliability and CO₂, and takes the cheapest viable one: 100 packs of 10 litres, exactly 1,000 litres, €1,332 at this hotel's own price. That's under the €1,500 limit, so it's auto-approved." |
| 0:45–0:55 | Switch kitchen to **Fell Lodge** and run the same request. Approval turns amber and shows R1. | "The same request at a lodge with an €800 limit stops, and a human taps approve. The mandate is checked again on Valio's side, at Valio's own fixed price, so a buyer agent can't get around it." |
| 0:55–1:20 | Plan from a menu: pick the **Hotel Aurora** sample and click **Build my Valio order**. Scroll the dish cards, then the deliveries. | "Now a full week. Five dishes and 730 covers become recipe cards, then one cart per delivery day. Every dish is marked cookable, substituted or missing. Fresh dill can't arrive in time, so it buys frozen dill and flags the swap rather than dropping the dish." |
| 1:20–1:35 | Open the **Decision log** tab and filter to Rules and holds. | "Every decision is in plain language: what was filtered and why, which rule held what, and who approved it." |
| 1:35–1:45 | Open the **For agents (MCP)** tab. | "The same brain is an open MCP server. A hotel chain's own procurement agent can call `request_order` with one sentence. Valio still enforces prices, assortment and approvals." |
| 1:45–2:00 | Open the **How we test it** tab. | "We built the eval first. On menus, 70% of dishes are fully cookable against an 8% keyword baseline, and 65% on recipes we never tuned on, with zero allergen violations. On buyer requests, 13 out of 13 pass on every one of three fresh runs, with zero false auto-approvals. Ordering from Valio, in one tap." |

Backup if the live API is slow: the milk request takes about 15 s cold and the menu about 60 s. Record each part separately and splice them.

# Live pitch, 5 minutes (Sunday peer review)

Before you start, have three tabs ready: the live site on Hotel Aurora with the menu sample already planned once (so it loads fast), the same site on the Order tab, and the GitHub README. Valio's handout sets the weights: demo 30%, user need 20%, autonomy and guardrails 20%, robustness 15%, openness 15%.

**0:00–0:40 · The need (user need, 20%)**
"A hotel kitchen orders from several wholesalers every week. To turn a menu into an order, a purchaser works out recipes, scales them to covers, finds the right pack sizes, checks allergens and delivery cut-offs, and gets sign-off over budget. That takes about an hour, and errors are expensive. Valio told us their goal is share of wallet: buyers stay with the supplier where ordering is effortless. So we built ordering that takes one paste and one tap, inside Valio's webshop. It is not a chatbot."

**0:40–2:10 · Live demo, Valio's own example (end-to-end demo, 30%)**
1. Quick request: "I need 1,000 litres of lactose-free milk by Monday." Point at the flow bar as it moves through Request, Lookup, Order and Approval.
2. "It searched 12,643 products locally. Allergen rules removed 33 milks this kitchen can't serve before the AI saw them. Then it priced only 8 products through Valio's API, because Valio asked us never to query the whole catalogue."
3. Open "Why this product". It compares three options on €/L, delivery reliability and CO₂, and picks the cheapest viable one: 100 × 10 L, exactly 1,000 L, €1,332 at this customer's price. That's within the €1,500 limit, so it is auto-approved.
4. Switch the kitchen to Fell Lodge and run the same request. It is held under R1, over the €800 limit. Tap "Approve as head chef".

**2:10–3:10 · The real job: a whole menu (demo)**
Open the planned Aurora week: 5 dishes and 730 covers, grouped into one cart per delivery day. Each dish is marked cookable, substituted or missing. Fresh dill can't arrive in time, so the agent bought frozen dill and flagged the swap. Then open the Decision log and filter to Rules and holds: "Every hold names its rule."

**3:10–3:50 · Trust (autonomy and guardrails, 20%, plus robustness, 15%)**
- "Guardrails work by construction. The AI never sees a product that breaks the kitchen's rules."
- "Code does the maths, not the model: pack sizes come from Valio's price API, quantities are rounded up to whole packs, and availability and cut-offs are checked."
- "Valio enforces the mandate on its own side. When an order is placed, every line is re-priced at Valio's fixed price, and a tampered price is rejected. The approval rules are applied again there, so a buyer's agent can't skip them."
- "It handles stock-outs in order: first Valio's own substitution links, then the same ingredient in another form, then a recipe-level swap that a person must approve, and only then a visible gap."

**3:50–4:30 · Proof (How we test it tab)**
- "We wrote the evals before the agent: 39 hand-written recipe cards and a scorer written independently of the agent."
- "Dishes fully cookable: 8% for a keyword baseline, 70% for the agent on dev, and 65% on recipes we never tuned on. Zero allergen violations."
- "On buyer requests, the set is balanced between cases where the agent should act alone and cases where it must stop. 13 of 13 pass on every one of three fresh runs, with zero false auto-approvals."
- "One honest failure: on held-out, it once bought berry purée for a pie. We fixed it and reported the number from before the fix."

**4:30–5:00 · Openness and path to production (15%)**
"The same brain is an open MCP server. A hotel chain's own procurement agent can call `request_order` in one sentence. To go to production, swap our mock order call for the webshop's order API. Kitchen policies come from the customer account, and both evals run in CI. Ordering from Valio, in one tap."

Likely questions:
- **"What if the AI hallucinates a product?"** It can only pick from a guarded shortlist, and every ID is checked against the catalogue again.
- **"Why not just a chatbot?"** A buyer wants a cart they can approve, not a conversation.
- **"Cost?"** About 5 to 30 small LLM calls per menu, cached.
