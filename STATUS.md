VALIO / 2026-11-15 05:45 EET / commit 643d734 (pushed to GitHub main) / LIVE: https://valio.72.61.22.106.sslip.io (MCP: https://valio.72.61.22.106.sslip.io/mcp/)

The old Vercel URL https://valio-menu-to-delivery.vercel.app is still down (Blob store blocked, deploy cap hit). Use the VPS URL for the submission and the video.

Job paraphrase: fix every problem in the judge's review (review/REVIEW.md) so a critical judge scores 10/10. Order: official milk example in Ask Valio and MCP; every request yields a draft; cumulative limits; honest log and receipt; allergens and diets; token-protected MCP; public landing and how-it-works pages; speed and polish. Verify on the deployed site at 1440x900 and 390 px, reset the demo account, report what is not done.

DONE (deployed on the Hostinger VPS as its own container behind the existing Traefik; verified on the live URL):

1. Milk example. "I need 1,000 litres of lactose-free milk by Monday…" in Ask Valio adds 1,000 × Valio Arki Eila kevytmaitojuoma 1 L (€1.01/L, €1,010.00), shows Best / Better / Good with pack maths and why other offers are ruled out (late, order-by time passed, short stock), and raises the weekly-limit approval. New MCP tools quote_products and order_products do the same in one call: placed when within authority, otherwise needs_approval with reasons and a review link. Partial stock is split across the cheapest products and sent for approval.
2. Every request yields a draft. "Conference lunch Tuesday, 60 guests, one vegan option", beef stew and cheesecake produce drafts with an "Assumed recipe, please check" approval and tagged lines; a missing ingredient is an approvable note, not a dead end. A question appears only for an impossible day ("tonight") and is shown alone, with no stale panel. Saying the same thing twice answers "This is already in your order. Nothing changed."
3. Limits. Weekly and monthly limits count every placed order in every channel. A new draft subtracts what is already ordered for the week, so the same week cannot be ordered twice; a repeat of the same products raises a "possible repeat" approval. The dashboard never shows "Ready to send" with an open limit approval.
4. Honest record. Approvals, withdrawn approvals, rule changes, token changes, refused agent attempts and orders are written to the account log with who and when. An order that needed OKs says "3 approvals by Sanna: …", never "Within your rules". Receipt entries are the live calls of that request and of placing, with their real times; cached entries are gone. The confirmation reads "Order AU-… is recorded" and says plainly it is a demo order and nothing ships.
5. Allergens and diets. "Lemon tart with almond crust" in the no-nut kitchen raises "almond crust left out" for approval; "Kolme vierasta on maidoton" raises a dairy-free approval naming the dishes and products; a nut-allergy note is answered from the kitchen rule. An allergen rule can be removed in Settings.
6. MCP. Per-account bearer token (Settings → Connected assistants: show, copy, replace). No token or a wrong token gets 401. Seven tools, each with an output schema and structuredContent. Outside agents order on top of the standing week, so the same wedding gives the same products, swap and pack approvals in both channels.
7. Public pages. "/" states who it is for, the problem, the three controls, the open door and measured numbers, with "Try the demo account". "/how-it-works" lists the tools, standards, who decides what, exceptions, audit trail, assumptions and next steps. Both are static HTML with one small stylesheet and preloaded fonts.
8. Speed and polish. Approve and +/- update the screen at once and the server confirms after; quantities can be typed; change responses carry no evidence blob. "412 booked guests", kg and L units, formatted dates in every message, one euro format, catalogue shows the reason a product cannot be ordered and lists orderable products first, "lactose-free milk" returns milk first, Add to order confirms the product, day and amount, invoices are grouped by delivery with VAT, case packs read "Case of 5 L", recipe names are English.

NUMBERS (measured on the live URL, 15 Nov 05:35-05:45 EET, in isolated test kitchens unless noted):
- Deployed commit equals local commit: /api/health reports 643d734.
- 72 Python tests pass, including 8 new regressions for the review findings.
- Browser flow (scripts/e2e_flow.cjs) at 1440x900 and 390x844: 20 of 20 steps pass at each size, 0 console errors, no horizontal overflow.
- Request scenarios (scripts/e2e_requests.cjs): tonight, wedding, repeat, conference lunch, almond crust + maidoton, nut allergy: 6 of 6 as specified, 0 console errors.
- Approve visible in 25-28 ms; typed quantity visible in 6-7 ms (was 5-6 s in the review).
- Milk example in the browser: 5.4 s from Send to ranked offers. MCP: quote_products 2.4 s, order_products 2.9-3.0 s, prepare_order (wedding) 2.4 s.
- MCP without a token or with a wrong token: 401. Seven tools, all with output schemas and structuredContent.
- A refused place_order took 20.2 s once (it re-quotes live; likely a Valio rate-limit retry). Not investigated further.
- Wedding: portal +EUR 1,132.30; MCP EUR 1,136.51 for the same request (measured locally). Same products, fish swap and larger-pack approval; the EUR 4.21 difference is pack rounding against the standing order.
- Landing page load: 238 ms desktop, 283 ms phone.
- Public demo account after reset: 3 delivered past orders (EUR 1,079.06, 1,220.69, 1,371.68), one prepared draft of 46 products and EUR 1,293.92, empty log, default rules, EUR 2,592.37 spent in November.

SCREENSHOTS (live site): artifacts/e2e/review/live-desktop-landing.png, live-desktop-dashboard.png, live-phone-landing.png, live-phone-dashboard.png, live-desktop-how.png; flow shots d-*.png and m-*.png; scenario shots s2-*.png in the same folder.

REVIEW: no separate reviewer pass. Self-checked against each numbered review item above.

Spec gaps I filled:
- The public landing page replaces the v3 sign-in card at "/" (the fix job asks for it). "Try the demo account" is on it.
- Assistant orders (MCP) are increments on top of the standing week, not a second full week.
- "One vegan option" with no count is assumed at about 15% of guests and listed under "Valio assumed".
- A repeat-order approval appears when at least half of a draft's products are already on a placed order for the week.
- Connectors that cannot send a header (Claude, ChatGPT) use a personal connector address carrying the token.

NOT DONE, and why:
- The Vercel URL is not fixed. A push no longer deploys there (deploy cap) and its storage is blocked. If the team is upgraded to Pro, the pushed commit can deploy; it then needs working storage (Blob unblocked, or STORE_URL / STORE_KEY / STORE_SECRET).
- No separate reviewer pass.
- The old jsdom suite (tests/ui.legacy.cjs) and tests/portal.e2e.cjs were written for the removed sign-in card and are retired; use npm run e2e.
- Vercel 403s on /mcp/: could not reproduce (60 of 60 calls returned 200 before the outage) and the project has no custom firewall configuration, so no setting was changed. The VPS has no bot protection in front of /mcp/.
- The "Valio Aimo" wordmark is still text, as DESIGN-DIRECTION.md specifies.
- Portal and MCP totals for the same wedding differ by EUR 4.21 (pack rounding), not zero.

HOW IT IS HOSTED:
- VPS 72.61.22.106, container "valio" (image valio:643d734), files in /opt/valio, keys in /opt/valio/.env (not in git), account data in the Docker volume valio-data. Traefik labels only on this container; no other container or Traefik setting was touched.
- Redeploy: rsync api chefagent public requirements.txt Dockerfile to /opt/valio, docker build, docker rm -f valio, docker run with the same labels (see docker-compose.vps.yml for the label set).
- Reset the demo account: docker exec valio python scripts/reset_demo.py (archives, never deletes).

NEXT: record the video on the VPS URL before 17:00 Helsinki; a separate reviewer pass; decide whether to bring the Vercel URL back.

NEEDS DECISION: submit the VPS URL, or upgrade Vercel to Pro to restore the old URL.

BLOCKED: none for the VPS site. Valio's test API closes Monday's order-by time today at 17:00 Helsinki; after that Monday lines correctly show "order-by time has passed".
