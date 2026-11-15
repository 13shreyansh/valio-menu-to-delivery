VALIO / 2026-11-15 05:30 EET / local commit on main, NOT pushed / https://valio-menu-to-delivery.vercel.app is DOWN (see BLOCKED)

Job paraphrase: fix every problem in the judge's review (review/REVIEW.md) so a critical judge scores 10/10. Order: official milk example in Ask Valio and MCP; every request yields a draft; cumulative limits; honest log and receipt; allergens and diets; token-protected MCP; public landing and how-it-works pages; speed and polish. Verify on the deployed site at 1440x900 and 390 px, reset the demo account, report what is not done.

DONE (all verified locally against the live Valio and Gemini APIs; nothing is deployed yet):

1. Milk example. "I need 1,000 litres of lactose-free milk by Monday…" in Ask Valio adds 1,000 × Valio Arki Eila kevytmaitojuoma 1 L (€1.01/L, €1,010.00), shows Best / Better / Good with pack maths and why other offers are ruled out (late, order-by time passed, short stock), and raises the weekly-limit approval. New MCP tools quote_products and order_products do the same in one call: placed when within authority, otherwise needs_approval with reasons and a review link. Partial stock is split across the cheapest products and sent for approval.
2. Every request yields a draft. "Conference lunch Tuesday, 60 guests, one vegan option", beef stew and cheesecake produce drafts with an "Assumed recipe, please check" approval and tagged lines; a missing ingredient is an approvable note, not a dead end. A question appears only for an impossible day ("tonight") and is shown alone, with no stale panel. Saying the same thing twice answers "This is already in your order. Nothing changed."
3. Limits. Weekly and monthly limits count every placed order in every channel. A new draft subtracts what is already ordered for the week, so the same week cannot be ordered twice; a repeat of the same products raises a "possible repeat" approval. The dashboard never shows "Ready to send" with an open limit approval.
4. Honest record. Approvals, withdrawn approvals, rule changes, token changes, refused agent attempts and orders are written to the account log with who and when. An order that needed OKs says "3 approvals by Sanna: …", never "Within your rules". Receipt entries are the live calls of that request and of placing, with their real times; cached entries are gone. The confirmation reads "Order AU-… is recorded" and says plainly it is a demo order and nothing ships.
5. Allergens and diets. "Lemon tart with almond crust" in the no-nut kitchen raises "almond crust left out" for approval; "Kolme vierasta on maidoton" raises a dairy-free approval naming the dishes and products; a nut-allergy note is answered from the kitchen rule. An allergen rule can be removed in Settings.
6. MCP. Per-account bearer token (Settings → Connected assistants: show, copy, replace). No token or a wrong token gets 401. Seven tools, each with an output schema and structuredContent. Outside agents order on top of the standing week, so the same wedding gives the same products, swap and pack approvals in both channels.
7. Public pages. "/" states who it is for, the problem, the three controls, the open door and measured numbers, with "Try the demo account". "/how-it-works" lists the tools, standards, who decides what, exceptions, audit trail, assumptions and next steps. Both are static HTML with one small stylesheet and preloaded fonts.
8. Speed and polish. Approve and +/- update the screen at once and the server confirms after; quantities can be typed; change responses carry no evidence blob. "412 booked guests", kg and L units, formatted dates in every message, one euro format, catalogue shows the reason a product cannot be ordered and lists orderable products first, "lactose-free milk" returns milk first, Add to order confirms the product, day and amount, invoices are grouped by delivery with VAT, case packs read "Case of 5 L", recipe names are English.

NUMBERS (all measured locally, 15 Nov 05:00–05:30 EET):
- 72 Python tests pass, including 8 new regressions for the review findings.
- Browser flow (scripts/e2e_flow.cjs) at 1440x900 and 390x844: 20 of 20 steps pass, 0 console errors, no horizontal overflow.
- Request scenarios (scripts/e2e_requests.cjs): tonight, wedding, repeat, conference lunch, almond crust + maidoton, nut allergy: 6 of 6 behave as specified, 0 console errors.
- Approve visible in 27–28 ms; typed quantity visible in 5–15 ms (was 5–6 s in the review).
- Milk example: 5.1 s in the engine, 9.9–11.9 s in the browser including the checklist (pacing since shortened); MCP order_products 4.3–4.6 s; quote_products 2.4 s.
- Wedding: portal +€1,132.30, MCP €1,136.51 for the same request. Same products, fish swap and larger-pack approval; the €4.21 difference is pack rounding against the standing order.
- Draft response about 120 KB before compression (was 430 KB per click, and clicks no longer wait for it).
- Baseline unchanged: 46 products, 3 deliveries, €1,293.92 for the prepared week.

SCREENSHOTS (local run): scratchpad shots d-landing.png, d-milk-result.png, d-order.png, m-sheet.png, s2-almond-order.png. They will be re-taken on the deployed site into artifacts/e2e/review/.

REVIEW: no separate reviewer pass yet. Self-checked against each numbered review item above.

Spec gaps I filled:
- The public landing page replaces the v3 sign-in card at "/" (the fix job asks for it). "Try the demo account" is on it.
- Assistant orders (MCP) are increments on top of the standing week, not a second full week.
- "One vegan option" with no count is assumed at about 15% of guests and listed under "Valio assumed".
- A repeat-order approval appears when at least half of a draft's products are already on a placed order for the week.
- Connectors that cannot send a header (Claude, ChatGPT) use a personal connector address carrying the token.

NOT DONE, and why:
- Not deployed and not verified on the live URL: see BLOCKED.
- Demo account not reset on the live store for the same reason. scripts/reset_demo.py is written and tested locally (archives week 47 orders, drafts and log, restores rules, rebuilds three past weeks through the order engine).
- The old jsdom suite (tests/ui.legacy.cjs) was written for the removed start card and hangs; it is retired, and the Playwright scripts cover those screens.
- tests/portal.e2e.cjs (Job 03) still targets the old start screen; use npm run e2e instead.
- Vercel 403s: I measured 60 of 60 MCP calls returning 200 and found no custom firewall configuration on the project (the Vercel API reports none), so no setting was changed. The review's 403s coincide with the storage block below.
- The "Valio Aimo" wordmark is still text, as DESIGN-DIRECTION.md specifies.

NEXT: deploy to the chosen host, run npm run e2e against it, reset the demo account, re-take screenshots.

NEEDS DECISION: where to host (VPS container, or Vercel after upgrading to Pro).

BLOCKED:
- The live site returns 503 after sign-in: Vercel blocked the project's Blob store ("Your store is blocked"). Old account data cannot be read.
- The Vercel team hit the 100 deploys/day cap, so a push will not deploy.
- This session's permission check refused creating a Supabase project, running SQL on it, and creating a Cloudflare D1 database. Ready alternatives: Dockerfile + docker-compose.vps.yml (account data on the container volume, nothing else needed), or Vercel with STORE_URL / STORE_KEY / STORE_SECRET, or Vercel Blob if Pro unblocks it.
- Valio's test API closes Monday's order-by time today at 17:00 Helsinki. After that, Monday lines correctly show "order-by time has passed".
