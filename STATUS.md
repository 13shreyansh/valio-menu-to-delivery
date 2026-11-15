VALIO / Sun 15 Nov 06:20 Helsinki / 70daa59 / https://valio.72.61.22.106.sslip.io

Job paraphrase: fix "Valio is unavailable" (Valio API rate limit), stress test the live site, fix every error and every issue from the independent re-judge (review/REVIEW-2.md, 5.55/10 before fixes), deploy only the valio container, reset the demo account.

DONE:
- Valio API: one shared, spaced queue, 6 tries with backoff, shared cache, last-30-min fallback logged as such, clear "busy, nothing changed" message, browser auto-retry. Root cause: HTTP 429 from junction26.valioaimo.fi, then r.json() on the error body.
- Each "Try the demo account" gets a private copy of Hotel Aurora (demo-<id>, own MCP token, own order numbers), seeded by scripts/reset_demo.py.
- Nuts/peanuts/sesame inferred from product names (undeclared almonds, hazelnuts blocked in UI and MCP); undeclared risky products need an OK; placed events keep their stock (wedding after a placed week is no longer EUR 0); diet notes include stock; event-named change reasons; unknown products and rule-excluded products say why; 50,000 L needs an amount check; one request per draft at a time; plain impossible-date answer; offers card, Drafts tab, 390 px how-it-works, no raw None/undefined.

NUMBERS (measured, stress run5 on 70daa59: 10 browser sessions 6x1440 + 4x390, 3 MCP clients):
- 220 UI steps, 60 Ask Valio requests: 0 failed steps, 0 HTTP 4xx/5xx, 0 console/page errors, 0 stale offers, 0 nut leaks, 0 duplicate order numbers. Ask Valio p50 5.6 s, p95 10.3 s. Server: 0 tracebacks, 0 429s.
- MCP: bad/no/garbage token 401; place_order refusals only where approval is required or the id is unknown.
- 80/80 unit tests (4 new regression tests).

SCREENSHOTS: scratchpad final-desktop-dashboard.png, final-mobile-dashboard.png, stress/run5/*.png (session tmp dir)
REVIEW: independent re-judge 5.55/10 before this round (review/REVIEW-2.md); not re-scored after fixes.
NEXT: re-judge on 70daa59; expire old demo copies (about 1,300 docs in SQLite now, harmless).
NEEDS DECISION: none
BLOCKED: none

Reset the demo account: docker exec valio python scripts/reset_demo.py (archives, never deletes; also refreshes the private-copy template).
Stress test: RUN_LABEL=runN node scripts/stress_live.cjs
