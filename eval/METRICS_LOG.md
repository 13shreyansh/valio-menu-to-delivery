# Metrics log

One row per change. Every change is general (prompt rule, retrieval, policy, rounding), never a per-dish fix.
Gold edits are logged as gold fixes. Held-out is run once per frozen version.

## A. Menu → cart (dev split: 10 cases, 37 dishes)

| Version | Change and why | Cookable | Ingredient recall | Allergen/diet violations | Qty within ±30% | Extra lines (€) |
|---|---|---|---|---|---|---|
| bm25_top1 (floor) | Same recipe step, top keyword hit, no LLM pick, no guardrails | 4/37 (5%) | 0.69 | 16 | | |
| no_guardrails | Full agent with the allergen/diet filter switched off | ~11/37 | | 11 | | |
| v0 | First full agent | 46% | 85.5% | 0 | 55% | 27 (€939) |
| v1 | Pick prompt accepts prepared forms of the same ingredient (diced onion, liquid egg, UHT). Only salt, pepper, oil and water count as pantry: spices, stock, sugar and herbs are bought | 62% | 91.1% | 0 | | 63 (€1,754) |
| v2 | Pack size: trust the printed pack when the price-API ratio agrees within 3% (that ratio is rounded to cents). Direct requests are never rounded below the asked quantity | see below | | | | |

Error analysis after v1 (first failure per dish, 14 failures):
- **Retrieval or pick** (6): onion ×2, mushroom ×2 in the nut-free kitchen, pork stew cut picked as beef, lemon picked as vinegar.
- **Fresh-herb stock-outs** (2): dill. One of these picked fennel for dill.
- **Quantity under the 80% bar** (2): curry powder 0.75, vegetable stock 0.6.
- **Gold rule gaps** (4): ham in category 17209, potato dices in 41751, burger patties, pork cutlet. These need a chef's spot check before any gold edit.

## B. Request → commitment → approval (13 cases, balanced)

This eval follows Valio's handout: a buyer's free-text request runs through intake, lookup, choice and policy. A code grader checks four things: the product, the quantity, on-time delivery, and the approval call. Expected calls are split 7 auto, 3 escalate and 3 refuse.

| Run | Change and why | pass@1 | pass^k | auto | escalate | refuse | False auto-approvals |
|---|---|---|---|---|---|---|---|
| r0 | First run | 0.75 | | 6/7 | 3/3 | 0/2 | 1 |
| r1 | **Criteria fix** (grader, not agent): "refuse" now means nothing is committed without a human. A safe alternative held for sign-off passes, because reading r0's traces showed the agent offering a nut-free swap or an oat drink for approval, which a buyer would want | 0.92 | | 6/7 | 3/3 | 2/2 | 0 |
| r2 | Bug: needs never carried the `direct` flag, so the cheapest-option rule and exact quantities did not fire. Also the 10 kg vs 9.98 kg pack fix from v2 | 1.00 | | 7/7 | 3/3 | 2/2 | 0 |
| r3 | Replaced a case that could not exercise its rule (direct requests have no "first choice" to swap). Added a total salmon stock-out (refuse) and 2,000 L of milk over the limit (escalate) | 1.00 | | 7/7 | 3/3 | 3/3 | 0 |
| r3-k3 | Same agent, 3 fresh LLM samples per case (no cache) | | | | | | |
