const { chromium } = require("playwright");
// Runs the real flow as a user would. Against a deployed site it uses an isolated
// test kitchen (x-valio-test-run), so the public demo account stays clean.
const base = process.env.BASE_URL || "http://localhost:8765";
const isolated = base.includes("localhost") ? {} : { extraHTTPHeaders: require("./test_kitchen.cjs")().headers };
const out = process.env.OUT || "artifacts/e2e/review";
require("fs").mkdirSync(out, { recursive: true });
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, ...isolated });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push("PAGE " + e.message));
  p.on("console", (m) => m.type() === "error" && errors.push("CONSOLE " + m.text()));
  const shot = (n, full = false) => p.screenshot({ path: `${out}/s2-${n}.png`, fullPage: full });
  await p.goto(base + "/"); await p.click("#demo"); await p.waitForSelector(".order-card h2", { timeout: 60000 });
  const ask = async (name, text, expectQuestion = false) => {
    const t = Date.now();
    try {
      if (!(await p.locator("#ask-input").count())) await p.click(".ask-open");
      await p.fill("#ask-input", text); await p.click('[data-action="send"]');
      await p.waitForSelector(expectQuestion ? ".ask-question" : ".ask-result", { timeout: 120000 });
      console.log("ok  ", name, Date.now() - t, "ms |", (await p.locator(expectQuestion ? ".ask-question" : ".ask-result").innerText()).replace(/\n/g, " ").slice(0, 200));
      await shot(name + "-drawer");
      if (!expectQuestion) {
        await p.click('.ask-result [data-action="review"]'); await p.waitForSelector(".approvals, .delivery-section");
        console.log("     approvals:", (await p.locator(".approval .approval-title").allInnerTexts()).join(" || ").slice(0, 600));
        console.log("     tags:", [...new Set(await p.locator(".tag").allInnerTexts())].join(" | "));
        await shot(name + "-order", true);
      }
    } catch (e) { console.log("FAIL", name, e.message.split("\n")[0]); await shot("fail-" + name); }
  };
  await ask("tonight", "Private dinner tonight for 20 guests, beef stew", true);
  await ask("wedding", "Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.");
  await ask("repeat", "Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.");
  await ask("conference", "Conference lunch Tuesday, 60 guests, one vegan option");
  await ask("almond", "Friday dinner for 40: lemon tart with almond crust and cheesecake. Kolme vierasta on maidoton.");
  await ask("nuts", "Two guests have a severe nut allergy");
  console.log("errors:", errors.length, errors.slice(0, 6));
  await b.close();
})();
