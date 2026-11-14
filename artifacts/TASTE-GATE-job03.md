# Job 03 TASTE-GATE

PASS against the Chief's five findings and the binding v3 direction on https://valio-menu-to-delivery.vercel.app, app revision `ff7f325`.

No separate TASTE-GATE rubric or command was present in the entry or shared Junction root. The reproducible local gate is `node scripts/taste_gate.cjs`, using the Chief's findings, DESIGN-DIRECTION.md and DESIGN-FLOOR.md. This is a scoped product/spec review, not a blanket accessibility certification.

| Check | Evidence |
| --- | --- |
| Clean Hotel Aurora | Measured: three past delivered weekly orders; November spend EUR2,592.37 of EUR6,000; remaining EUR3,407.63. Same ledger before/after isolated ordering tests. |
| Account isolation | Browser, background Ask Valio work and outside HTTPS MCP client share only their run-specific test kitchen. Unit and live rule tests verify separation. Legacy polluted orders are reversibly archived. |
| Compact order card | Measured: 24px between the final delivery row and actions at both widths. No reserved blank band. |
| Approved decision rows | Distinct swap, pack and spend titles remain with approval time and Undo. Quantity edit reopens affected approvals. |
| Plain receipt | Real catalogue count and check time; supplier prices/stock in kitchen language. Endpoint paths and raw JSON are confined to Details. |
| Every page | Measured: 36 screenshots, 18 screens at 1440x900 and 390x844, no document overflow or console errors. Includes every navigation page, settings subpage, past order and invoice view. |
| Phone exceptions | Sign-in card fits; Why links stay within their rows. Secondary tables and settings navigation scroll horizontally inside their containers. |
| Bell | Targeted recapture awaited the real account refresh; measured three past events at both widths and zero console errors. |

Machine evidence is in `artifacts/e2e/job03/taste-gate.json` and `bell-check.json`; screenshots are alongside them. The full ordering flow screenshots and outside-client receipt are in `artifacts/e2e/`.

The direction's exact ink-3 colour conflicts with the floor's text-contrast target. Inferred from its specified colours: approximately 3.66:1 on white and 3.39:1 on the canvas, below 4.5:1. The binding palette was preserved; no general accessibility PASS is claimed.

Historical kitchen lifecycle dates and cover counts are authored sample-account data. Each order was prepared, approved and placed through the real order engine, using current real Valio prices; actual supplier evidence remains unchanged. These are not historical supplier invoices. The inbuilt browser host was unavailable, so verification used the explicitly required headless browser. Physical microphone use and a real Claude connector chat remain unverified.
