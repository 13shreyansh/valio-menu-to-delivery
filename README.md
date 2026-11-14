# Valio Aimo kitchen ordering portal

Live: https://valio-menu-to-delivery.vercel.app

Hotel Aurora's weekly order is computed from its recipes, bookings and current stock. Valio supplies real customer prices, stock, available dates, pack comparisons and cut-offs. Ask Valio interprets typed requests, microphone recordings and photographs through Gemini. The chef reviews the actual supply, pack and spend decisions before placing an order.

The remote MCP server uses the same engine and account rules. Outside assistants can find products, check prices and stock, prepare orders and place orders within their authority. Confirmation stores the order in the private account ledger. The sponsor has no order API, so nothing ships.

## Run

Use process environment variables `VALIO_API_KEY`, `GEMINI_API_KEY`, and `BLOB_READ_WRITE_TOKEN`. Never write credentials into the repository. Vercel already has the entry's credentials and private Blob store connected.

```
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
npm ci
.venv/bin/python -m uvicorn api.index:app --port 8077
```

Without Blob credentials, local development uses SQLite at `/tmp/valio-aurora.sqlite`. Vercel refuses to fall back to temporary storage. Private Blob documents use conditional ETag writes to prevent lost updates. Draft IDs are random and orders are idempotent by draft ID. An immutable order snapshot is saved before its pointer commits to the ledger, so a failed convenience-draft write cannot alter the recorded price on retry. Pending assistant drafts are indexed for chef review. Each confirmed order retains its exact prices and receipt.

The demo-account sign-in uses an expiring, HttpOnly, same-site cookie. The MCP endpoint is deliberately public and scoped only to this synthetic account. It accepts no arbitrary customer identifier, chef identity or caller-supplied approval. Do not use this public demo connector for a production kitchen.

## Quality commands

```
.venv/bin/python -m pytest -q
npm test
npm run check
npx playwright test
.venv/bin/python scripts/mcp_client.py https://valio-menu-to-delivery.vercel.app
node scripts/verify_media.cjs
node scripts/verify_controls.cjs
```

`verify_media.cjs` passes the synthetic voice fixture through the browser's actual MediaRecorder and Gemini, then uploads a menu photograph. It verifies the recording and interpretation pipeline; it does not represent a physical microphone test. `verify_controls.cjs` saves rules through the real controls, verifies web and MCP blocking, opens an assistant draft, restores the original rules, adds a catalogue item, and opens an invoice. Run it separately from the main acceptance suite because the demo account is shared.

The Python supplier fixtures and JSDOM fixtures are synthetic test data and are never served by the product. The Playwright test uses the deployed URL and actual Valio/Gemini responses. `BASE_URL` may override it for local verification. Screenshots, console reports and measured MCP results go to `artifacts/e2e/`.

`portal.py` enforces current weekly-order limits, swap approval, allergen restrictions and larger-change thresholds for every web and MCP mutation. Approval fingerprints bind current rules, products, pack quantities and prices. A quantity edit reopens affected approvals; fresh quotes at commitment invalidate changed prices. A “Don't allow” limit, missing supply, past cut-off or recipe shortage cannot be approved away.

The weekly limit applies to each weekly order, matching the setting's “When an order goes over” language. It is not a cumulative account spending cap. The monthly account summary includes all stored confirmations. A cumulative cap would block the spec's subsequent outside-assistant order after the chef approves an over-limit wedding order, so this interpretation is recorded in the spec gaps.

## Data provenance and spec gaps

Hotel Aurora's menus, guest counts, stock, recipes, team and historical quantities are authored sample account records. Historical account totals are computed from those quantities and actual Valio customer prices, checked at account initialization. They are sample invoices, not supplier invoices. Kitchen profile and invoice details state this.

The Valio availability API supplies available dates and supplier cut-offs, but no arrival times. The portal says “Arrival time to confirm” rather than inventing 07:00. Requested delivery days are the account's connected schedule. A product is accepted only if Valio confirms availability by that day and its cut-off has not passed.

The actual wedding supply decision currently concerns unavailable salmon and an available recipe-safe trout fillet. The actual cheaper cream pack is 1.75 L. The spec's whitefish, pike-perch and 10 L examples are not fabricated when the live data differs.

The built-in browser host was unavailable during implementation. The explicitly requested Playwright acceptance uses headless Chromium. Physical microphone use and the real Claude custom-connector recording remain separate manual checks.

## MCP

Streamable HTTP: https://valio-menu-to-delivery.vercel.app/mcp/

Tools: `find_products`, `check_stock_and_prices`, `prepare_order`, `place_order`.

The outside client script initializes MCP, lists tools, quotes a product, prepares “breakfast for 40 for Wednesday”, and places the returned draft. It uses HTTPS and no browser cookies or approval overrides. The browser acceptance verifies its resulting order in Orders, Recent orders and the bell.
