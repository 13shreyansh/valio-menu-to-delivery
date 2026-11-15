# Valio completed cutover, historical operator handoff

Completed on 15 November 2026 after separate review and Cloudinary account verification. Do not rerun these commands against the current deployment. This record preserves the reviewed sequence. The verified application/image is frozen at `e648c83cf8f057df9467c4f7cde12f3771c906a6`.

The current canary is `valio-sponsors-e648c83`, on private port 8078 and https://valio-sponsor.72.61.22.106.sslip.io. The sequence below replaced production successfully. The current `valio` uses Aiven; the original is retained stopped as `valio-sqlite-before-e648c83`. The initial import and optimized pre-catch-up matched 1596/1596 source documents. Optimized unchanged catch-up took 47.861 seconds, measured, with no pool shutdown warning.

## Ordered commands on the VPS

1. Keep the canary running. Gracefully stop the old SQLite writer:

```bash
docker stop --time 60 valio
```

2. Apply and verify the last source delta:

```bash
docker exec valio-sponsors-e648c83 python scripts/migrate_aiven.py --apply
```

If this command fails, restart `valio` and stop the cutover. No production Aiven writes have been introduced at this point, so this rollback is safe.

3. Feed the five provider values from the canary's Docker environment to the existing staging helper in memory, exactly as for the earlier canary replacement. Do not print or save the JSON. Use these exact arguments:

```bash
python3 /opt/valio-sponsors/releases/e648c83cf8f057df9467c4f7cde12f3771c906a6/scripts/stage_sponsors.py \
  --image valio-sponsors:e648c83cf8f0 \
  --commit e648c83cf8f057df9467c4f7cde12f3771c906a6 \
  --name valio-live-e648c83 \
  --port 8079 \
  --ca /opt/valio-sponsors/certs/aiven-ca.pem \
  --url https://valio.72.61.22.106.sslip.io
```

The helper still inspects the stopped original `valio` container, preserving its supplier/model/signing settings and mounting its SQLite documents read-only. The new container uses Aiven and its own Traefik router. No shared proxy restart is needed. This invocation sets the production PUBLIC_URL, so connected-assistant addresses do not point at the preview host.

4. Check production `/api/health` for the exact full commit, `aiven-postgresql`, Cloudinary and ElevenLabs. Run the actual production browser acceptance using private visitor kitchens:

```bash
BASE_URL=https://valio.72.61.22.106.sslip.io \
EXPECTED_COMMIT=e648c83cf8f057df9467c4f7cde12f3771c906a6 \
AUDIO_FIXTURE=artifacts/media/sponsor-request.wav \
OUT=artifacts/e2e/sponsors-production-e648c83 \
node scripts/sponsor-e2e.cjs
```

5. After health and acceptance pass, preserve the old container and restore the normal operational name without restarting the new service:

```bash
docker rename valio valio-sqlite-before-e648c83
docker rename valio-live-e648c83 valio
```

After production accepts real Aiven writes, never revert to the old SQLite-only image without reconciling those orders. Media-only failures can be handled by keeping the Aiven-capable image and changing media configuration, rather than downgrading storage. Retain both earlier stopped canaries and the original SQLite volume until the owner decides their retention.

## Evidence

- `artifacts/e2e/sponsors-e648c83/acceptance.json`: real 1440/390 flow passed; eight captures reviewed; zero page errors.
- `artifacts/sponsors/PROVIDER-ACCEPTANCE.md`: real provider acceptance, attributed to the coordinating agent.
- Latest local suite: 94/94 unit regressions passed, measured. JS syntax, Python compile and whitespace checks passed.

The Cloudinary hackathon survey is a separate sponsor requirement. This job did not submit it or change Junction descriptions or submissions.

Final production browser, fresh-order worker-restart and MCP checks passed. See [the release record](RELEASE-e648c83.md) for the final evidence and current rollback constraint.
