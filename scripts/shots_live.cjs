const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const base = "https://valio.72.61.22.106.sslip.io"; const out = "artifacts/e2e/review";
  const errors = [];
  for (const [tag, vp] of [["live-desktop", { width: 1440, height: 900 }], ["live-phone", { width: 390, height: 844 }]]) {
    const p = await (await b.newContext({ viewport: vp, deviceScaleFactor: 2 })).newPage();
    p.on("pageerror", (e) => errors.push(e.message)); p.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    const t = Date.now(); await p.goto(base + "/", { waitUntil: "load" }); console.log(tag, "landing load ms", Date.now() - t);
    await p.screenshot({ path: `${out}/${tag}-landing.png` });
    await p.click("#demo"); await p.waitForSelector(".recent tbody tr", { timeout: 60000 });
    console.log(tag, (await p.locator(".order-card").innerText()).replace(/\n/g, " | ").slice(0, 260));
    await p.screenshot({ path: `${out}/${tag}-dashboard.png` });
    await p.goto(base + "/how-it-works"); await p.screenshot({ path: `${out}/${tag}-how.png` });
  }
  console.log("errors", errors); await b.close();
})();
