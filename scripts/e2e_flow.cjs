const { chromium } = require("playwright");
// Runs the real flow as a user would. Against a deployed site it uses an isolated
// test kitchen (x-valio-test-run), so the public demo account stays clean.
const base = process.env.BASE_URL || "http://localhost:8765";
const isolated = base.includes("localhost") ? {} : { extraHTTPHeaders: require("./test_kitchen.cjs")().headers };
const out = process.env.OUT || "artifacts/e2e/review";
require("fs").mkdirSync(out, { recursive: true });
const phone = process.env.PHONE === "1";
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, ...isolated });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push("PAGE " + e.message));
  p.on("console", (m) => m.type() === "error" && errors.push("CONSOLE " + m.text()));
  const tag = phone ? "m-" : "d-";
  const shot = (n, full = false) => p.screenshot({ path: `${out}/${tag}${n}.png`, fullPage: full });
  const step = async (name, fn) => { const t = Date.now(); try { await fn(); console.log("ok  ", name, Date.now() - t, "ms"); } catch (e) { console.log("FAIL", name, e.message.split("\n")[0]); await shot("fail-" + name.replace(/\W+/g, "-")); } };
  await p.goto(base + "/"); await shot("landing"); await shot("landing-full", true);
  await p.goto(base + "/how-it-works"); await shot("how");
  await p.goto(base + "/");
  await step("login", async () => { await p.click("#demo"); await p.waitForSelector(".order-card h2", { timeout: 60000 }); });
  await shot("dashboard");
  await step("ask milk", async () => {
    await p.click(".ask-open"); await p.fill("#ask-input", "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability.");
    await p.click('[data-action="send"]'); await p.waitForTimeout(2500); await shot("milk-working");
    await p.waitForSelector(".ask-result", { timeout: 90000 });
  });
  await shot("milk-result");
  await step("review", async () => { await p.click('.ask-result [data-action="review"]'); await p.waitForSelector(".approvals"); });
  await shot("order");
  await step("why", async () => { await p.click('tr[data-row^="extra-"] [data-action="why"]'); await p.waitForSelector(".why-popover"); });
  await shot("why"); await p.keyboard.press("Escape");
  await step("approve fast", async () => { const t = Date.now(); await p.click('.approval [data-action="approve"]'); await p.waitForSelector(".approval.approved"); console.log("     approve visible in", Date.now() - t, "ms"); });
  await step("typed qty", async () => { const i = p.locator(".qty-input").first(); const t = Date.now(); await i.fill("7"); await i.press("Enter"); await p.waitForFunction(() => document.querySelector(".qty-input").value === "7"); console.log("     qty visible in", Date.now() - t, "ms"); await p.waitForTimeout(3500); });
  await shot("order-after-edit");
  await step("receipt", async () => { await p.click('[data-action="receipt"]'); await p.waitForSelector(".receipt-entry", { timeout: 20000 }); });
  await shot("receipt"); await p.click('[data-action="close-drawer"]');
  await step("approve all + place", async () => {
    for (let i = 0; i < 8; i++) { const a = p.locator('.approval:not(.approved) [data-action="approve"]'); if (!(await a.count())) break; await a.first().click(); await p.waitForTimeout(300); }
    await p.waitForFunction(() => !document.querySelector('[data-action="place"]').disabled, null, { timeout: 30000 });
    await p.click('[data-action="place"]'); await p.waitForSelector(".confirmation", { timeout: 60000 });
  });
  await shot("confirmation");
  await step("dashboard after", async () => { await p.click('.confirmation [data-action="dashboard"]'); await p.waitForSelector(".order-card h2", { timeout: 60000 }); });
  await shot("dashboard-after");
  await step("bell", async () => { await p.click('[data-action="bell"]'); await p.waitForSelector(".events .event"); });
  await shot("bell"); await p.keyboard.press("Escape");
  for (const [name, path, sel] of [["orders", "/orders", ".table"], ["catalogue", "/catalogue", ".table tbody tr td.money"], ["deliveries", "/deliveries", ".table"], ["invoices", "/invoices", ".table"], ["rules", "/settings/rules", ".rule-section"], ["connected", "/settings/connected-ai", ".copy-row"], ["kitchen", "/settings/kitchen", ".card"]]) {
    await step(name, async () => { await p.goto(base + path); await p.waitForSelector(sel, { timeout: 60000 }); await p.waitForTimeout(400); }); await shot(name);
  }
  await step("overflow", async () => { const w = await p.evaluate(() => document.documentElement.scrollWidth); if (w > (phone ? 390 : 1440)) throw Error("overflow " + w); });
  console.log("errors:", errors.length, errors.slice(0, 8));
  await b.close();
})();
