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
