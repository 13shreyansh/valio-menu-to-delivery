/* Integration test: synthetic voice through real MediaRecorder + Gemini, and a real photo upload.
   This verifies the browser pipeline, not a physical microphone or live speaker. */
const { chromium, expect } = require("@playwright/test");
const path = require("node:path");
const fs = require("node:fs");
(async () => {
  const base = process.argv[2] || "https://valio-menu-to-delivery.vercel.app";
  const b = await chromium.launch({
    headless: true,
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      "--use-file-for-fake-audio-capture=" +
        path.resolve("tests/fixtures/wedding-test.wav"),
    ],
  });
  const kitchen = require("./test_kitchen.cjs")();
  const ctx = await b.newContext({
    extraHTTPHeaders: kitchen.headers,
    viewport: { width: 1440, height: 900 },
    permissions: ["microphone"],
  });
  const p = await ctx.newPage();
  p.setDefaultTimeout(30000);
  const errors = [];
  const report = {
    source:
      "synthetic voice through real MediaRecorder and Gemini; physical microphone unverified",
  };
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  try {
    await p.goto(base);
    console.log("Opened start screen");
    await p
      .getByRole("button", {
        name: "Try the demo account (Hotel Aurora)",
        exact: true,
      })
      .click();
    console.log("Signed in request");
    await p
      .getByRole("button", { name: "Review order", exact: true })
      .waitFor({ timeout: 60000 });
    console.log("Loaded dashboard");
    await p.getByRole("button", { name: "Ask Valio", exact: true }).click();
    console.log("Opened Ask Valio");
    await p
      .getByRole("button", { name: "Start recording", exact: true })
      .click();
    console.log("Clicked record");
    await expect(p.getByText("Listening…", { exact: true })).toBeVisible({
      timeout: 30000,
    });
    await p.waitForTimeout(4000);
    report.level_measured = Number(
      await p
        .locator("#audio-level")
        .evaluate((el) => parseFloat(el.style.width)),
    );
    await p.screenshot({ path: "artifacts/media/recording.png" });
    await p.waitForTimeout(7000);
    await p
      .getByRole("button", { name: "Stop recording", exact: true })
      .click();
    await expect(p.locator("#ask-input")).toHaveValue(/salmon soup/i, {
      timeout: 120000,
    });
    const transcript = await p.locator("#ask-input").inputValue();
    expect(transcript).toMatch(/whitefish/i);
    expect(transcript).toMatch(/lemon tart/i);
    report.transcript = transcript;
    await p.screenshot({ path: "artifacts/media/transcript.png" });
    await p.getByRole("button", { name: "Send", exact: true }).click();
    await expect(p.locator(".ask-result")).toContainText(
      "3 things need your OK",
      { timeout: 180000 },
    );
    report.speech_order = "passed";
    console.log("Speech order passed");
    await p
      .locator("#photo-file")
      .setInputFiles("public/whiteboards/menu-1.jpg");
    await p.getByRole("button", { name: "Send", exact: true }).click();
    console.log("Sent photo");
    await expect(p.locator(".ask-result")).toBeVisible({ timeout: 180000 });
    await expect(p.locator(".drawer-body")).toContainText(
      /Juustolautanen|Cheese board/i,
    );
    await p.screenshot({ path: "artifacts/media/photo-result.png" });
    report.photo = "passed";
    const draftId = await p.evaluate(
      (key) => localStorage.getItem(key),
      "valio-draft-v3:test-" + kitchen.run,
    );
    const r = await ctx.request.get(base + "/api/drafts/" + draftId);
    const o = await r.json();
    const eventServices = o.services.filter((s) => s.wedding);
    expect(eventServices.filter((s) => s.recipe === "soup")).toHaveLength(0);
    expect(eventServices.find((s) => s.recipe === "cheeseboard").covers).toBe(
      140,
    );
    expect(eventServices.filter((s) => s.recipe === "tart")).toHaveLength(1);
    report.photo_event_services = eventServices;
    expect(errors).toEqual([]);
    report.console_errors = errors;
    console.log(JSON.stringify(report, null, 2));
  } catch (e) {
    report.error = e.message;
    report.mic_error = await p.evaluate(() => window.micError || null);
    await p.screenshot({ path: "artifacts/media/failure.png" });
    throw e;
  } finally {
    fs.writeFileSync(
      "artifacts/media/results.json",
      JSON.stringify(report, null, 2),
    );
    await b.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
