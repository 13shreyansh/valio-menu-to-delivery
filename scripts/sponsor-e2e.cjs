/* Real deployed provider flow. Each viewport gets a private visitor kitchen. */
const { chromium } = require("playwright");
const { strict: assert } = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.BASE_URL;
const expected = process.env.EXPECTED_COMMIT;
const audioPath = process.env.AUDIO_FIXTURE;
if (!base || !expected || !audioPath) throw Error("Set BASE_URL, EXPECTED_COMMIT and AUDIO_FIXTURE");
const out = process.env.OUT || "artifacts/e2e/sponsors";
fs.mkdirSync(out, { recursive: true });
const photoPath = path.resolve("public/whiteboards/menu-3.jpg");

(async () => {
  const health = await fetch(base + "/api/health").then(r => r.json());
  assert.equal(health.build_commit, expected, "Test the intended deployed commit");
  assert.equal(health.storage_backend, "aiven-postgresql");
  assert.equal(health.cloudinary, true);
  assert.equal(health.elevenlabs, true);
  const browser = await chromium.launch({ args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream", "--use-file-for-fake-audio-capture=" + path.resolve(audioPath)] });
  const results = [];
  try {
    for (const width of [1440, 390]) {
      const context = await browser.newContext({ viewport: { width, height: width === 390 ? 844 : 900 }, permissions: ["microphone"] });
      const page = await context.newPage();
      page.setDefaultTimeout(30000);
      const errors = [];
      page.on("pageerror", e => errors.push(e.message));
      const shots = [];
      const shot = async name => { const file = path.join(out, `${width}-${name}.png`); await page.screenshot({ path: file }); shots.push(file); };
      await page.goto(base);
      await page.locator("#demo").click();
      await page.locator(".order-card h2").waitFor({ state: "visible", timeout: 60000 });
      await shot("dashboard");
      await page.locator(".ask-open").click();
      await page.getByRole("button", { name: "Start recording", exact: true }).click();
      await page.getByRole("button", { name: "Stop recording", exact: true }).waitFor({ state: "visible" });
      // The synthetic fixture lasts seven seconds. This is actual recorded audio sent to Scribe.
      await page.waitForTimeout(7800);
      const transcription = page.waitForResponse(r => r.url().endsWith("/api/transcribe") && r.request().method() === "POST");
      await page.getByRole("button", { name: "Stop recording", exact: true }).click();
      const transcriptResponse = await transcription;
      assert.equal(transcriptResponse.status(), 200);
      const transcript = await transcriptResponse.json();
      assert.equal(transcript.provider, "ElevenLabs");
      assert.match(transcript.transcript, /wedding/i);
      await page.waitForFunction(() => document.querySelector("#ask-input")?.value.toLowerCase().includes("wedding"));
      await shot("voice-transcript");
      await page.locator('[data-action="send"]').click();
      await page.locator(".ask-result").waitFor({ state: "visible", timeout: 120000 });
      await page.locator('.ask-result [data-action="review"]').click();
      await page.locator(".delivery-section").first().waitFor({ state: "visible" });

      await page.locator(".ask-open").click();
      const upload = page.waitForResponse(r => r.url().endsWith("/api/media/menu") && r.request().method() === "POST");
      await page.locator("#photo-file").setInputFiles(photoPath);
      const uploadResponse = await upload;
      assert.equal(uploadResponse.status(), 200);
      const receipt = await uploadResponse.json();
      assert.equal(receipt.provider, "Cloudinary");
      assert.equal(receipt.type, "authenticated");
      const image = page.getByAltText("Your attached menu photo");
      await image.waitFor({ state: "visible" });
      await page.waitForFunction(() => { const i = document.querySelector('img[alt="Your attached menu photo"]'); return i?.complete && i.naturalWidth > 0; });
      assert.ok(await image.evaluate(e => e.naturalWidth <= 960 && e.naturalHeight <= 960));
      assert.match(await image.getAttribute("src"), /^https:\/\/res\.cloudinary\.com\//);
      await shot("saved-menu-photo");
      await page.locator('[data-action="send"]').click();
      await page.locator(".ask-result").waitFor({ state: "visible", timeout: 120000 });
      await page.locator('.ask-result [data-action="review"]').click();
      for (let i = 0; i < 16; i++) {
        const approvals = page.locator('.approval:not(.approved) [data-action="approve"]');
        if (!await approvals.count()) break;
        await Promise.all([
          page.waitForResponse(r => /\/api\/drafts\/[^/]+\/change$/.test(r.url()) && r.request().method() === "POST"),
          approvals.first().click(),
        ]);
      }
      await page.waitForFunction(() => { const b = document.querySelector('[data-action="place"]'); return b && !b.disabled; }, null, { timeout: 30000 });
      await page.locator('[data-action="place"]').click();
      await page.locator(".confirmation h1").waitFor({ state: "visible", timeout: 90000 });
      const number = (await page.locator(".confirmation h1").innerText()).match(/AU-[A-Z0-9]+/)[0];
      const speech = page.waitForResponse(r => r.url().endsWith("/spoken-confirmation"));
      await page.getByRole("button", { name: "Listen to confirmation", exact: true }).click();
      const spoken = await speech;
      assert.equal(spoken.status(), 200);
      assert.ok((await spoken.body()).length > 1000);
      await page.locator('audio[aria-label="Spoken order confirmation"]').waitFor({ state: "visible" });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Spoken-confirmation controls overflow the screen");
      await shot("spoken-confirmation");
      await page.goto(base + "/orders");
      await page.getByText(number, { exact: true }).first().waitFor({ state: "visible", timeout: 60000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.deepEqual(errors, []);
      results.push({ width, pass: true, voiceProvider: transcript.provider, photoProvider: receipt.provider, thumbnailLoaded: true, spokenConfirmation: true, storedOrderReloaded: true, pageErrors: 0, screenshots: shots });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const report = { pass: true, commit: health.build_commit, storage: health.storage_backend, scope: "private test kitchens", results };
  fs.writeFileSync(path.join(out, "acceptance.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
})().catch(error => { console.error(error.message); process.exitCode = 1; });
