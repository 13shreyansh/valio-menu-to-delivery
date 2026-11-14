# Metrics log

One row per change. Every change is general (prompt rule, retrieval, policy, rounding), never a per-dish fix.
Gold edits are logged as gold fixes. Held-out is run once per frozen version.

## A. Menu → cart (dev split: 10 cases, 37 dishes)

| Version | Change and why | Cookable | Ingredient recall | Allergen/diet violations | Qty within ±30% | Extra lines (€) |
|---|---|---|---|---|---|---|
| bm25_top1 (floor) | Same recipe step, top keyword hit, no LLM pick, no guardrails | 3/37 (8%) | 0.69 | 16 | 47% | 59 (€4,925) |
| no_guardrails | Full agent with the allergen/diet filter switched off | 11/37 (30%) | 0.84 | 11 | 56% | 28 (€1,153) |
| v0 | First full agent | 46% | 85.5% | 0 | 55% | 27 (€939) |
| v1 | Pick prompt accepts prepared forms of the same ingredient (diced onion, liquid egg, UHT). Only salt, pepper, oil and water count as pantry: spices, stock, sugar and herbs are bought | 62% | 91.1% | 0 | | 63 (€1,754) |
| v2 | Pack size: trust the printed pack when the price-API ratio agrees within 3% (that ratio is rounded to cents). Direct requests are never rounded below the asked quantity | 62% (no change, no regression) | 91.1% | 0 | 57% | 63 (€1,754) |
| v3 | Hypothesis from error analysis: 3 of 14 failures were fresh herbs/citrus that Valio cannot deliver in time, and the agent jumped straight to a recipe substitute (lemon to vinegar, dill to fennel). New step before any recipe change: retry the **same ingredient in another form** (frozen, dried, juice, puree), flagged as a same-ingredient swap. Pass rule set in advance: cookable up, violations stay 0, request eval stays 13/13 | **70.3%** (26/37) | 92.7% | 0 | 54% | €1,887 |

**Held-out, frozen v2** (6 cases, 23 dishes, 14 recipe cards never used while tuning; run once): **70% cookable (16/23)**, 88.3% ingredient recall, **0 allergen violations**, 0 unflagged recipe swaps, quantities within ±30%: 70%. No sign of overfitting to dev (dev is 62%).

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
| r3-k3 | Same agent, 3 fresh LLM samples per case (no cache) | 1.00 | **1.00 (pass^3)** | 7/7 | 3/3 | 3/3 | 0 |
| r4 | Regression check after v3 (other-form step does not apply to direct requests) | 1.00 | | 7/7 | 3/3 | 3/3 | 0 |

## C. Valio-side mandate check (submit_order)

Before: submit only re-checked allergens, substitutions and the spend limit, using the buyer's own prices, so a draft with an
estimated pack size (R4) or a may-contain flag (R3) could be placed without a human. Now submit re-prices every line through
Valio's price API (a changed or tampered price is rejected: the commitment is at Valio's fixed price), re-checks delivery by
the date, and applies R1 to R4 itself. Tested: a tampered unit price is rejected; 1,000 L of milk for Fell Lodge (EUR 800 limit)
is held until approved_by is given.

Known limitation after v3: a dried herb replaces the fresh herb at the same weight (dried needs about a third), and a small need can
open a big frozen pack (10 kg coriander). Both are visible on the line and flagged as swaps for the chef.
