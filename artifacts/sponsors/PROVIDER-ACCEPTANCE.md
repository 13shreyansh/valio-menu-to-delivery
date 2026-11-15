# Provider acceptance before the canary release

The coordinating agent ran the real provider probes with runtime-only credentials and the public Aiven CA. No credentials or signed photo URLs are copied into this record.

| Check | Recorded result | Provenance |
| --- | --- | --- |
| Aiven PostgreSQL | PASS: one concurrent winner and one conflict; separate connection read; isolated private clone; no token clone; safe source catch-up; concurrent cloud overwrite refused; atomic import rollback. Probe duration 8.328 seconds. | Measured by the coordinating agent using scripts/verify_sponsors.py --database. |
| Cloudinary | PASS: authenticated 1100 x 780 menu upload, signed resized preview decoded at 960 x 681. Probe duration 3.514 seconds. | Measured by the coordinating agent using the real photo probe. |
| ElevenLabs | PASS: Scribe transcribed the wedding/Saturday audio fixture and the confirmation response contained 115399 audio bytes. Probe duration 2.539 seconds; no order action. | Measured by the coordinating agent using the real speech probe. |
| Unit regressions | 93/93 PASS after the pool-lifecycle and canary-router changes. | Measured locally in this worktree. |

The first provider processes exposed slow pool-worker shutdown warnings after successful checks. Explicit cleanup now runs on success, failure and server shutdown; three lifecycle regressions pass. The coordinating agent should rerun a real probe to confirm clean process exit.

These probes do not replace the deployed browser acceptance. Cloudinary account claiming is still pending, so global image delivery remains a release gate. No production replacement or portal change is authorized by this record.
