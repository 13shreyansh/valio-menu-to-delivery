/* Stress test of the live site: parallel browser sessions doing the full flow with real UI
   actions, plus MCP clients (scripts/stress_mcp.cjs). Every session signs into the demo account
   in its own private copy of Hotel Aurora (since bdc9b60 every /api/login makes one), so the
   public demo stays clean. ISOLATE=1 additionally sends an x-valio-test-run header per session.
   Usage: node scripts/stress_live.cjs
   Env:   BASE_URL (default live VPS), SESSIONS (10), MCP_CLIENTS (3), OUT (results dir),
          RUN_LABEL (name of this run inside OUT). Writes OUT/<label>/results.json + screenshots. */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const { randomUUID } = require("node:crypto");
const { runMcp } = require("./stress_mcp.cjs");

const base = (process.env.BASE_URL || "https://valio.72.61.22.106.sslip.io").replace(/\/$/, "");
const N = +(process.env.SESSIONS || 10);
const MCP_N = +(process.env.MCP_CLIENTS || 3);
const ISOLATE = process.env.ISOLATE === "1";
const label = process.env.RUN_LABEL || "run-" + new Date().toISOString().replace(/[:.]/g, "-");
const outRoot = process.env.OUT || "/private/tmp/claude-501/-Users-shreyansh-Documents-ChatGPT-Junction/c3436647-3dbb-4a8e-a1e7-7c4ee12c0e16/scratchpad/stress";
const out = path.join(outRoot, label);
fs.mkdirSync(out, { recursive: true });
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a);

// expect: what a correct answer looks like. "question" = a helpful question is the right answer.
const ASKS = [
  { id: "milk", text: "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability.", expect: "result" },
  { id: "wedding", text: "Wedding for 120 guests on Saturday: salmon soup, whitefish with potatoes, lemon tart", expect: "result" },
  { id: "conference", text: "Conference lunch for 80 on Wednesday with one vegan option", expect: "result" },
  { id: "almond", text: "Lemon tart with almond crust for 40 on Friday", expect: "result" }, // nut rule: checked on the order's approvals (S.nutHandled)
  { id: "milk50", text: "Milk for 50 people tomorrow", expect: "either" },
  { id: "yesterday", text: "Deliver 20 kg butter yesterday", expect: "question" },
];
const BAD_TEXT = [
  [/\bundefined\b/, "undefined"], [/\bnull\b/, "null"], [/\bNaN\b/, "NaN"], [/\[object /, "[object"],
  [/Traceback/, "Traceback"], [/\{\s*"[A-Za-z_]+"\s*:/, "raw JSON"], [/Infinity/, "Infinity"], [/Invalid Date/, "Invalid Date"],
];

async function session(browser, idx) {
  const phone = idx >= 6;
  const run = randomUUID().replaceAll("-", "");
  const S = { idx, phone, kitchen: ISOLATE ? "test-" + run : "private demo copy", steps: [], http: [], console: [], pageErrors: [], requestFailed: [], banners: [], badText: [], asks: [], shots: [] };
  const ctx = await browser.newContext({ viewport: phone ? { width: 390, height: 844 } : { width: 1440, height: 900 }, ...(ISOLATE ? { extraHTTPHeaders: { "x-valio-test-run": run } } : {}) });
  const p = await ctx.newPage();
  p.setDefaultTimeout(30000);
  let where = "start";
  p.on("console", (m) => m.type() === "error" && S.console.push({ where, text: m.text().slice(0, 400), url: p.url() }));
  p.on("pageerror", (e) => S.pageErrors.push({ where, text: String(e.message).slice(0, 400), url: p.url() }));
  p.on("requestfailed", (r) => { const f = r.failure()?.errorText || ""; if (!/ERR_ABORTED/.test(f)) S.requestFailed.push({ where, url: r.url(), error: f }); });
  p.on("response", async (r) => {
    if (r.status() < 400) return;
    let body = "";
    try { body = (await r.text()).slice(0, 300); } catch {}
    S.http.push({ where, url: r.url().replace(base, ""), method: r.request().method(), status: r.status(), body });
  });
  const tag = `s${String(idx).padStart(2, "0")}${phone ? "m" : "d"}`;
  const shot = async (name) => { const f = path.join(out, `${tag}-${name.replace(/\W+/g, "-")}.png`); try { await p.screenshot({ path: f }); S.shots.push(f); } catch {} return f; };
  const seen = new Set();
  const scan = async (at) => {
    let d;
    try {
      d = await p.evaluate(() => {
        const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
        const alerts = [...document.querySelectorAll('[role=alert], .error, .ask-question, .toast, .status-note')].filter(vis).map((e) => ({ cls: e.className, role: e.getAttribute("role") || "", text: e.innerText.trim().slice(0, 400) }));
        return { alerts, text: document.body.innerText, overflow: document.documentElement.scrollWidth };
      });
    } catch { return; }
    for (const a of d.alerts) {
      const key = a.cls + a.text;
      if (seen.has(key) || !a.text) continue;
      seen.add(key);
      S.banners.push({ where: at, ...a, shot: await shot("banner-" + at) });
    }
    for (const [re, name] of BAD_TEXT) {
      const m = d.text.match(re);
      if (m && !seen.has("bad" + name + at)) {
        seen.add("bad" + name + at);
        const i = d.text.indexOf(m[0]);
        S.badText.push({ where: at, kind: name, context: d.text.slice(Math.max(0, i - 80), i + 80).replace(/\s+/g, " "), shot: await shot("badtext-" + at) });
      }
    }
    if (d.overflow > (phone ? 390 : 1440) + 1 && !seen.has("ovf" + at)) { seen.add("ovf" + at); S.steps.push({ name: "overflow@" + at, ok: false, err: "horizontal overflow " + d.overflow + "px", shot: await shot("overflow-" + at) }); }
  };
  const step = async (name, fn) => {
    where = name;
    const t0 = Date.now();
    try { await fn(); S.steps.push({ name, ok: true, ms: Date.now() - t0 }); }
    catch (e) { S.steps.push({ name, ok: false, ms: Date.now() - t0, err: String(e.message).split("\n")[0].slice(0, 300), shot: await shot("fail-" + name) }); }
    await scan(name);
  };
  const openAsk = async () => { if (!(await p.locator("#ask-input").count())) await p.locator(".ask-open").first().click(); await p.locator("#ask-input:not([disabled])").waitFor(); };
  const outcome = (text) => p.waitForFunction((t) => {
    const d = document.querySelector('.drawer[aria-label="Ask Valio"]');
    if (!d) return false;
    const rb = d.querySelector(".request-block");
    if (!rb || !rb.innerText.startsWith(t.slice(0, 40)) || d.querySelector(".working")) return false;
    const r = d.querySelector(".ask-result"), q = d.querySelector(".ask-question");
    return r ? "result" : q ? (q.getAttribute("role") === "alert" ? "error" : "question") : false;
  }, text, { timeout: 180000, polling: 250 });
  const ask = async (a, { dbl = false, reload = false } = {}) => {
    const rec = { session: idx, id: a.id, text: a.text, expect: a.expect };
    S.asks.push(rec);
    await step("ask-" + a.id, async () => {
      await openAsk();
      await p.fill("#ask-input", a.text);
      const t0 = Date.now();
      if (dbl) await p.locator('[data-action="send"]').dblclick(); else await p.click('[data-action="send"]');
      if (reload) {
        await p.waitForTimeout(1500);
        await p.reload();
        rec.reloaded = true;
        await p.waitForSelector(".order-card h2, .approvals, main table, .delivery-section", { timeout: 60000 }).catch(() => {});
        await scan("after-reload-" + a.id);
        // What happens to an in-flight request after a reload: resend it as a user would.
        await openAsk();
        await p.fill("#ask-input", a.text);
        await p.click('[data-action="send"]');
      }
      const h = await outcome(a.text);
      rec.ms = Date.now() - t0;
      rec.outcome = await h.jsonValue();
      rec.reply = (await p.locator('.drawer[aria-label="Ask Valio"] .drawer-body').innerText()).replace(/\s+/g, " ").slice(0, 700);
      const ok = a.expect === "either" ? rec.outcome !== "error" : rec.outcome === a.expect;
      rec.asExpected = ok;
      // An offers panel from an earlier product request must not appear under a dish request.
      if (!/milk|butter/i.test(a.text) && /Offers compared/.test(rec.reply)) { rec.staleOffers = true; rec.shot = await shot("ask-stale-offers-" + a.id); }
      if (!rec.asExpected) rec.shot = await shot("ask-unexpected-" + a.id);
    });
  };
  const approveAll = async (dbl) => {
    for (let i = 0; i < 12; i++) {
      const a = p.locator('.approval:not(.approved) [data-action="approve"]');
      if (!(await a.count())) return i;
      if (dbl && i === 0) await a.first().dblclick(); else await a.first().click();
      await p.waitForTimeout(350);
    }
    throw Error("approvals still open after 12 clicks");
  };
  const dbl = idx % 3 === 0; // sessions 0,3,6,9 double-click buttons
  const reloadMid = idx % 4 === 1; // sessions 1,5,9 reload during a request
  try {
    await step("landing", async () => { await p.goto(base + "/"); await p.waitForSelector("#demo"); });
    await step("demo-login", async () => { await p.click("#demo"); await p.waitForSelector(".order-card h2", { timeout: 90000 }); });
    for (const [i, a] of ASKS.entries()) await ask(a, { dbl: dbl && i === 2, reload: reloadMid && i === 1 });
    await step("review", async () => {
      await openAsk().catch(() => {});
      const r = p.locator('.drawer [data-action="review"]');
      if (await r.count()) await r.first().click(); else { await p.goto(base + "/dashboard"); await p.waitForSelector(".order-card h2", { timeout: 60000 }); await p.locator('main [data-action="review"]').first().click(); }
      await p.waitForSelector(".approvals, .delivery-section", { timeout: 60000 });
      S.approvalTitles = await p.locator(".approval .approval-title").allInnerTexts().catch(() => []);
      S.nutHandled = (await p.locator(".approval").allInnerTexts()).some((t) => /almond/i.test(t) && /nut/i.test(t));
      if (!S.nutHandled) await shot("nut-rule-missing");
    });
    await step("approve-all", async () => { S.approvalsClicked = await approveAll(dbl); });
    await step("edit-qty-after-approve", async () => {
      const i = p.locator(".qty-input").first();
      const v = +(await i.inputValue());
      await i.fill(String(v + 3)); await i.press("Enter");
      await p.waitForFunction((x) => document.querySelector(".qty-input").value === String(x), v + 3);
      await p.waitForTimeout(3000);
      if (dbl) { await p.locator('[data-action="qty"][aria-label^="More"]').first().dblclick(); await p.waitForTimeout(2500); }
    });
    await step("why-popover", async () => { await p.locator('[data-action="why"]').first().click(); await p.waitForSelector(".why-popover"); await p.keyboard.press("Escape"); });
    await step("how-decided", async () => { await p.click('[data-action="receipt"]'); await p.waitForSelector(".receipt-entry", { timeout: 30000 }); await p.click('[data-action="close-drawer"]'); });
    await step("re-approve", async () => { S.reapprovals = await approveAll(false); });
    await step("place-order", async () => {
      await p.waitForFunction(() => { const b = document.querySelector('[data-action="place"]'); return b && !b.disabled; }, null, { timeout: 30000 });
      if (dbl) await p.locator('[data-action="place"]').dblclick(); else await p.click('[data-action="place"]');
      await p.waitForSelector(".confirmation", { timeout: 90000 });
      S.confirmation = (await p.locator(".confirmation h1").innerText()).trim();
    });
    await step("receipt-of-placed", async () => {
      await p.goto(base + "/orders"); await p.waitForSelector("[data-open-order]", { timeout: 60000 });
      S.ordersListed = await p.locator("tr[data-open-order]").count();
      await p.locator("tr[data-open-order]").first().click();
      await p.click('[data-action="receipt"]'); await p.waitForSelector(".receipt-entry", { timeout: 30000 });
      await p.click('[data-action="close-drawer"]');
    });
    await step("catalogue-search", async () => {
      await p.goto(base + "/catalogue"); await p.waitForSelector("#catalogue-search input");
      await p.fill("#catalogue-search input", "lactose-free milk");
      if (dbl) await p.locator('#catalogue-search [data-action="search"]').dblclick(); else await p.click('#catalogue-search [data-action="search"]');
      await p.waitForSelector("tbody tr td.money", { timeout: 90000 });
    });
    for (const [name, url, sel] of [["deliveries", "/deliveries", "main table, main .card"], ["invoices", "/invoices", "main table"], ["settings-rules", "/settings/rules", ".rule-section"], ["settings-connected", "/settings/connected-ai", ".copy-row"], ["dashboard", "/dashboard", ".order-card h2"]])
      await step(name, async () => { await p.goto(base + url); await p.waitForSelector(sel, { timeout: 60000 }); await p.waitForTimeout(500); if (name === "settings-connected") { const tg = p.locator('[data-action="toggle-token"]'); if (await tg.count()) await tg.first().click(); } });
    await shot("final");
  } catch (e) { S.steps.push({ name: "session", ok: false, err: e.message.slice(0, 300) }); }
  await ctx.close();
  log(`session ${idx} (${phone ? "390" : "1440"}) done: ${S.steps.filter((s) => !s.ok).length} failed steps, ${S.http.length} http>=400, ${S.console.length} console`);
  return S;
}

(async () => {
  const t0 = Date.now();
  log(`stress ${label}: ${N} browser sessions + ${MCP_N} MCP clients against ${base}`);
  const health = await (await fetch(base + "/api/health")).json().catch(() => ({}));
  const browser = await chromium.launch();
  const [sessions, mcp] = await Promise.all([
    Promise.all(Array.from({ length: N }, (_, i) => new Promise((r) => setTimeout(r, i * 400)).then(() => session(browser, i)))),
    runMcp(base, MCP_N, log, ISOLATE),
  ]);
  await browser.close();
  const res = { label, base, health, started: new Date(t0).toISOString(), ms: Date.now() - t0, sessions, mcp };
  fs.writeFileSync(path.join(out, "results.json"), JSON.stringify(res, null, 2));
  // Short summary
  const asks = sessions.flatMap((s) => s.asks).filter((a) => a.ms);
  const ms = asks.map((a) => a.ms).sort((a, b) => a - b);
  const pct = (q) => ms.length ? ms[Math.min(ms.length - 1, Math.floor(q * ms.length))] : null;
  const http = sessions.flatMap((s) => s.http);
  console.log(JSON.stringify({
    out, health: health.build_commit, sessions: N, asks: asks.length, p50: pct(0.5), p95: pct(0.95),
    "4xx": http.filter((h) => h.status < 500).length, "5xx": http.filter((h) => h.status >= 500).length,
    console: sessions.reduce((n, s) => n + s.console.length, 0), pageErrors: sessions.reduce((n, s) => n + s.pageErrors.length, 0),
    banners: sessions.reduce((n, s) => n + s.banners.length, 0), failedSteps: sessions.flatMap((s) => s.steps.filter((x) => !x.ok).map((x) => `s${s.idx}:${x.name}`)),
    staleOffers: asks.filter((a) => a.staleOffers).map((a) => `s${a.session}:${a.id}`),
    nutRuleMissing: sessions.filter((s) => s.nutHandled === false).map((s) => "s" + s.idx),
    duplicateOrderNumbers: Object.entries(sessions.reduce((m, s) => (s.confirmation && (m[s.confirmation] = (m[s.confirmation] || 0) + 1), m), {})).filter(([, n]) => n > 1).map(([k, n]) => `${k} x${n}`),
    unexpectedAsks: asks.filter((a) => !a.asExpected).map((a) => `s${a.session}:${a.id}=${a.outcome}`),
    mcpErrors: mcp.clients.flatMap((c) => c.errors.map((e) => `c${c.client}:${e.name}`)), mcpAuth: mcp.auth.map((a) => a.name + "=" + a.status),
  }, null, 1));
})();
