# How we test the agent

Valio's booth told us what success means: **when the delivery arrives, the kitchen can cook the whole menu.**
So the headline metric is not "did the chatbot answer", it is a deterministic check of the cart against
hand-written recipe cards.

## What is in the eval

| Piece | File | Size |
|---|---|---|
| Gold ingredient rules: which Valio products are an acceptable buy for an ingredient (category code + name rules) | `gold/ingredients.py` | 120 ingredients |
| Gold recipe cards: grams per portion for each component, essential or not, allowed substitutes | `gold/dishes.py` | 39 dishes (25 dev, 14 held-out) |
| Cases: menus as a hotel chef writes them, covers, diet tags, kitchen rules, supply disruptions | `gold/cases.py` | 16 cases (10 dev, 6 held-out) |
| Scorer (independent of the agent's code) | `score.py` | |
| Runner + baselines | `run.py` | |

Held-out dishes never appear in dev menus. The held-out split can only be run when `eval/FROZEN`
exists, which records the frozen version; we run it once per frozen version and do not tune on it.

## Metrics

- **Cookable rate**: share of dishes where every essential component is covered by an acceptable product,
  in at least 80% of the gold quantity, deliverable by the service date (re-checked against the API),
  with no allergen/diet violation. A recipe-level substitute counts only if it is flagged for human approval.
- **Ingredient recall**: share of essential components covered.
- **Allergen/diet violations**: re-derived by `score.py` with its own rules from the raw GS1 allergen
  codes (contains / may contain), claims and category codes. Target: **0**.
- **Quantity error**: ordered-for-dish kg vs gold kg; median |ratio - 1| and share within ±30%.
- **Extra lines / €**: products no gold component asked for (waste or noise).
- **Unflagged recipe substitutes**: must be 0 (guardrail check).

## Disruptions (dynamic environment)

Disruption cases re-use a menu and, through a seeded overlay on top of Valio's real availability
answers, take a share of the acceptable products for an ingredient out of stock or make them arrive
late. The agent must find another acceptable product, use Valio's substitution links, or propose a
recipe-compatible substitute that goes to a human.

## Protocol (no optimising the wrong thing)

1. Baselines first: `bm25_top1` (same recipe step, top keyword hit, no guardrails) and `no_guardrails`.
2. Every change is run on all dev cases and logged in `METRICS_LOG.md` with what changed and why.
3. Changes must be general (prompt rules, retrieval, policy), never per-dish fixes. Gold files are
   only edited to fix a gold bug, logged as such.
4. Price/stock answers are cached on first fetch so runs are comparable; the live app always calls the API.
5. Freeze, run held-out once, report it next to dev.
6. Spot checks: `spot_checks.csv` samples ingredient → product decisions for a human to grade, to catch
   cases where the gold rules themselves are wrong.

## Limits we know about

- The gold cards and rules were written by us (with an AI assistant) from standard foodservice
  proportions and Valio's data; a chef should review them, which is what the spot-check sheet is for.
- The gold rules use Valio's category codes, whose names are not published; groups were identified by
  inspecting their members.
- Availability is Valio's simulated mock API, so stock-out patterns are synthetic.
