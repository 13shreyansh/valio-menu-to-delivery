# Valio Aimo · The Kitchen Sheet

Live: https://valio-menu-to-delivery.vercel.app

A hotel chef's weekly order arrives already written. The Kitchen Sheet expands recipes into grams per cover, deducts kitchen stock, rounds to Valio sales units, and checks customer prices, availability and cut-offs. Tell Valio reads a typed or spoken wedding request through Gemini. A photograph of the final menu becomes an editable proposal before it changes the order.

The authored demo kitchen has menus, recipes, bookings, stock, handling rules and a chef-set weekly budget. Those fixtures are labelled in “Your kitchen, connected” and the decision receipt. Prices, supply, pack confirmation and cut-offs come from the sponsor API. Finnish catalogue names are preserved.

“Place order” is a demo confirmation. Nothing ships: the Junction API has no order endpoint. Confirmation and the technical receipt say this explicitly.

## Run locally

Set `VALIO_API_KEY` and `GEMINI_API_KEY` in the process environment through your secret manager. Do not write credentials to files. Optional `KITCHEN_SIGNING_KEY` separates sheet signing from the API credential. Optional `CHEF_MODEL` selects the Gemini model, defaulting to the model already configured by the data layer.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
npm ci
.venv/bin/python -m uvicorn api.index:app --port 8077
```

The catalogue is downloaded from Valio on a cold start and remains untracked. Vercel downloads it into temporary storage. Quote cache entries include customer identity, expire after 120 seconds, and are bypassed when placing the demo order. Server-signed sheet state expires after four hours, allowing stateless Vercel execution.

## Quality commands

```sh
.venv/bin/python -m pytest -q
npm test
npm run check
.venv/bin/python scripts/verify_live.py
```

The Python suite uses an explicitly synthetic supplier to test the hand-built expected product/pack order, weekly budget locking, quantity and price invalidation, allergen safety, passed cut-offs, cache isolation and unreadable photographs. No test price is served in the product.

`npm test` generates its own synthetic sheet fixture and runs DOM interactions in JSDOM. This is not a browser layout or microphone test.

`verify_live.py` uses the deployed app, actual Valio responses and actual Gemini understanding. It checks the expected wedding order, budget lock, three positive and two negative handwritten-style whiteboard fixtures, final demo confirmation and MCP. It writes the measured report to `artifacts/live-verification.json`. On first recording, its verified readings for “Play the story” go to `public/story-readings.json`; prices and approvals are still computed normally during playback.

Real browser acceptance at 1440 × 900, 1024 × 768 and 390 px, console checks and microphone capture must be checked through Codex's inbuilt browser. The present environment reports its browser host unavailable; no substitute personal or external browser has been used.

## Ordering controls

- Recipe substitutions preserve cooking method, fish weight and allergens, and need the chef's OK. The frozen trout fillet is portioned in the kitchen before poaching.
- Larger cream packs are proposed only when their quoted price per litre is lower and booked demand supports the kitchen's 48-hour opened-pack rule. The story uses all 14 l by Sunday breakfast.
- Weekly spend approval binds the entire order, including every product, amount and price. Editing a checked product reopens its check. A fresh quote at commitment invalidates stale approvals.
- Allergen violations, unavailable supply, passed cut-offs, insufficient stock and recipe shortages cannot be approved away.
- Unreadable photographs leave the order unchanged. An uncertain but partly legible menu requires in-place correction and explicit confirmation; a blank/garbled result cannot be relabelled as readable.

## MCP

Streamable HTTP: https://valio-menu-to-delivery.vercel.app/mcp/

The original tools remain available: `request_order`, `plan_menu_order`, `search_products`, `get_product`, `quote`, `find_substitutes`, `submit_order`. The legacy `submit_order` also returns an explicitly labelled mock confirmation. Tools use customer-specific prices and catalogue rules.

## Main files

- `chefagent/kitchen_fixtures.py`: kitchen, recipes, stock, catalogue shortlist and bookings.
- `chefagent/kitchen.py`: quantities, pack selection, guardrails, signed state, approvals and commitment.
- `chefagent/kitchen_intake.py`: Gemini multimodal understanding and deterministic validation.
- `chefagent/kitchen_routes.py`: sheet, speech, photo and story HTTP routes.
- `public/`: self-hosted font, Kitchen Sheet UI, handwritten-style whiteboards and recorded story readings.
- `tests/test_wedding.py`: independently authored golden product IDs and sales-unit counts.
