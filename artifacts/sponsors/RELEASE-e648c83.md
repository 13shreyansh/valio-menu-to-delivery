# Valio sponsor release verification

Application commit `e648c83cf8f057df9467c4f7cde12f3771c906a6` is live at https://valio.72.61.22.106.sslip.io. Documentation commits after this release do not imply a runtime redeployment.

## Checks completed on 15 November 2026

| Check | Result and scope |
| --- | --- |
| Unit regressions | Measured 94/94 pass. Includes missing-seed visitor isolation, concurrent ledger updates, provider validation, context-preserving threadpool routes and clean pool shutdown. JavaScript syntax and Python compilation passed. |
| CRACI | [Run 43687469639](https://github.com/13shreyansh/valio-menu-to-delivery/actions/runs/43687469639) succeeded using the CRACI runner. |
| Independent review | The coordinating agent reported separate 6 Astra spec and build passes on this application release. Initial findings about shared-account fallback and blocking async provider calls were fixed and covered by regressions before release. |
| Real provider probes | Aiven concurrent winner/conflict, separate connection read, private cloning without token reuse, safe catch-up and atomic rollback passed. Cloudinary authenticated 1100 × 780 upload produced a decoded 960 × 681 preview. ElevenLabs returned a wedding/Saturday transcript and 115399 bytes of confirmation audio. These probes were run by the coordinating agent. |
| Production browser flow | Measured 1440 × 900 and 390 × 844 pass, zero page exceptions. Actual microphone fixture → ElevenLabs → Gemini menu update → Cloudinary upload and loaded preview → menu update → approvals → order record → ElevenLabs audio → saved-order reload. Eight loaded screenshots were inspected. |
| Fresh-process persistence | A new private visitor prepared a wedding draft and placed order AU-9BC841D5. The actual production container restarted; its PID and start time changed. The retained browser session reloaded and opened the same immutable order receipt from Aiven, with zero page exceptions. |
| MCP regression | Authenticated initialize and tools/list passed with seven tools. An unauthenticated request returned 401. No MCP order action was issued by this probe. |
| Cutover | Measured 1596/1596 source documents matched after the final writer pause. No changed source rows remained. Writer pause to healthy production took 51.939 seconds. The prior SQLite container remains stopped and retained. |

The fresh-order restart check replaces an earlier baseline-receipt check. Baseline template receipts can have the same historical order number in different private copies; the final check creates a new order before restarting the worker.

## Local inspection records

The full-resolution captures and machine receipts remain in the release worktree, not in the public repository, to keep private account details and signed media URLs out of published evidence.

- `artifacts/e2e/sponsors-production-e648c83/acceptance.json` and its eight screenshots.
- `artifacts/e2e/persistence-production-fresh-e648c83/persistence.json` and `order-after-worker-restart.png`.
- `artifacts/sponsors/MCP-PRODUCTION-e648c83.json`.

These are integration checks, not a held-out recognition benchmark or a prize decision. Supplier orders remain application test records and nothing ships. The separate Cloudinary hackathon survey was not submitted by this release task. Junction portal entries and descriptions were not changed.

## Operation after cutover

Production uses the Aiven-capable image `valio-sponsors:e648c83cf8f0`, with the public CA mounted and provider secrets supplied through runtime configuration. The application health endpoint reports the full release commit and `aiven-postgresql` storage. Preserve the canonical production URL and signing identity on restart or replacement.

After production accepts Aiven writes, the stopped SQLite runtime is a retained source, not a safe immediate rollback target. Reconcile newer orders before any storage downgrade. A media-only incident should retain the Aiven-capable runtime and adjust the affected media configuration.
