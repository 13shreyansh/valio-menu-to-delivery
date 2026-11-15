# Provider acceptance

The coordinating agent ran the real provider probes with runtime-only credentials and the public Aiven CA. No credentials or signed photo URLs are copied into this record.

| Check | Recorded result | Provenance |
| --- | --- | --- |
| Aiven PostgreSQL | PASS: one concurrent winner and one conflict; separate connection read; isolated private clone; no token clone; safe source catch-up; concurrent cloud overwrite refused; atomic import rollback. Probe duration 8.328 seconds. | Measured by the coordinating agent using `scripts/verify_sponsors.py --database`. |
| Cloudinary | PASS: authenticated 1100 × 780 menu upload, signed resized preview decoded at 960 × 681. Probe duration 3.514 seconds. | Measured by the coordinating agent using the real photo probe. |
| ElevenLabs | PASS: Scribe transcribed the wedding/Saturday audio fixture and the confirmation response contained 115399 audio bytes. Probe duration 2.539 seconds; no order action. | Measured by the coordinating agent using the real speech probe. |
| Unit regressions | 94/94 PASS, including pool lifecycle, visitor isolation and safe bulk catch-up. | Measured locally in this worktree. |

The first provider processes exposed slow pool-worker shutdown warnings after successful checks. Explicit cleanup now runs on success, failure and server shutdown. The final unchanged source catch-up completed without a pool warning.

Cloudinary account claiming and email verification completed before production cutover. The final application passed real provider browser flows at both desktop and phone widths, plus fresh-order persistence across an actual production worker restart. See [the release record](RELEASE-e648c83.md).

The separate Cloudinary hackathon survey remains an administrative requirement. This task did not submit it or change Junction portal entries or descriptions.
