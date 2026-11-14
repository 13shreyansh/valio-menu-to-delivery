/* Deployed Job 03 screenshot gate. Read-only audit of Hotel Aurora; no test orders. */
const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
(async () => {
  const base = process.argv[2] || "https://valio-menu-to-delivery.vercel.app";
  fs.mkdirSync("artifacts/e2e/job03", { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = {
    gate: "Job 03 findings + DESIGN-DIRECTION.md v3 + DESIGN-FLOOR.md",
    official_taste_gate:
      "No separate rubric/command supplied; this is the reproducible local screenshot gate",
    base,
    checks: [],
    screenshots: [],
    console_errors: [],
  };
  let baseline;
  for (const [name, viewport] of [
    ["desktop", { width: 1440, height: 900 }],
    ["phone", { width: 390, height: 844 }],
  ]) {
    const ctx = await browser.newContext({ viewport });
    const p = await ctx.newPage();
    p.setDefaultTimeout(30000);
    p.on("pageerror", (e) => report.console_errors.push(e.message));
    p.on("console", (m) => {
      if (m.type() === "error") report.console_errors.push(m.text());
    });
    await ctx.route("**/api/**", async (route) => {
      const r = route.request();
      const path = new URL(r.url()).pathname;
      if (
        r.method() === "POST" &&
        !["/api/login", "/api/drafts"].includes(path)
      )
        throw Error("Read-only Aurora audit refused " + path);
      await route.continue();
    });
    const shot = async (label) => {
      await p.evaluate(() => document.fonts.ready);
      await p.waitForTimeout(180);
      const text = await p.locator("body").innerText();
      expect(text).not.toMatch(
        /Not supplied|\/api\/|undefined|Play the story|coming soon/i,
      );
      const metrics = await p.evaluate(() => ({
        pageWidth: document.documentElement.scrollWidth,
        viewport: innerWidth,
        font: getComputedStyle(document.body).fontFamily,
        background: getComputedStyle(document.body).backgroundColor,
      }));
      expect(metrics.pageWidth).toBeLessThanOrEqual(viewport.width);
      expect(metrics.font).toMatch(/Hanken/);
      const path = `artifacts/e2e/job03/${name}-${label}.png`;
      await p.screenshot({ path, fullPage: false });
      report.screenshots.push(path);
      report.checks.push({ name, screen: label, metrics });
    };
    const go = async (label) => {
      if (
        await p
          .getByRole("button", { name: "Open menu", exact: true })
          .isVisible()
      )
        await p.getByRole("button", { name: "Open menu", exact: true }).click();
      await p
        .locator(".sidebar")
        .getByRole("link", { name: label, exact: true })
        .click();
    };
    await p.goto(base);
    await shot("start");
    await p
      .getByRole("button", {
        name: "Try the demo account (Hotel Aurora)",
        exact: true,
      })
      .click();
    await expect(
      p.getByRole("button", { name: "Review order", exact: true }),
    ).toBeVisible({ timeout: 180000 });
    const account = await (await ctx.request.get(base + "/api/account")).json();
    expect(account.account_id).toBe("aurora");
    const ids = account.orders.map((o) => o.order_number);
    expect(new Set(ids).size).toBe(ids.length);
    expect(account.orders).toHaveLength(3);
    expect(
      account.orders.every(
        (o) =>
          o.status === "Delivered" &&
          o.deliveries.every((d) => new Date(d.date) < new Date()),
      ),
    ).toBe(true);
    const spent = account.orders
      .filter((o) => o.placed_at.startsWith("2026-11"))
      .reduce((s, o) => s + o.total, 0);
    expect(spent).toBeGreaterThan(0);
    expect(spent).toBeLessThan(account.rules.monthly_limit);
    const fingerprint = JSON.stringify(
      account.orders.map((o) => [
        o.order_number,
        o.total,
        o.placed_at,
        o.status,
      ]),
    );
    if (baseline) expect(fingerprint).toBe(baseline);
    else baseline = fingerprint;
    report.aurora = {
      orders: ids,
      november_spent_measured: Number(spent.toFixed(2)),
      monthly_limit: account.rules.monthly_limit,
      remaining_measured: Number(
        (account.rules.monthly_limit - spent).toFixed(2),
      ),
    };
    const gap = await p.evaluate(() => {
      const c = document.querySelector(".order-card");
      const a = c.querySelector(".order-actions").getBoundingClientRect();
      const d = [...c.querySelectorAll(".delivery-mini")]
        .at(-1)
        .getBoundingClientRect();
      return a.top - d.bottom;
    });
    expect(Math.abs(gap - 24)).toBeLessThan(1);
    report.checks.push({ name, card_action_gap_measured: gap });
    await shot("dashboard");
    await p.getByRole("button", { name: "Ask Valio", exact: true }).click();
    await shot("ask-empty");
    await p
      .getByRole("button", { name: "Close Ask Valio", exact: true })
      .click();
    await p.getByRole("button", { name: "Review order", exact: true }).click();
    await shot("order");
    await p
      .getByRole("button", { name: "How this was decided", exact: true })
      .click();
    await expect(p.locator(".receipt")).toBeVisible();
    await shot("receipt");
    await p.getByRole("button", { name: "Close receipt", exact: true }).click();
    await go("Orders");
    for (const tab of ["Placed", "Drafts", "Delivered"]) {
      await p.getByRole("button", { name: tab, exact: true }).click();
      await shot("orders-" + tab.toLowerCase());
    }
    await p.locator("main tbody tr").first().locator("a").click();
    await expect(
      p
        .locator(".topbar h1, .mobile-title")
        .filter({ hasText: /^Order AU-/ })
        .first(),
    ).toBeVisible({ timeout: 60000 });
    await expect(p.locator(".day-header").first()).toContainText("delivered");
    await shot("past-order");
    expect(
      await p.getByRole("button", { name: "Place order", exact: true }).count(),
    ).toBe(0);
    await go("Catalogue");
    await p
      .getByRole("textbox", { name: "Search products or codes", exact: true })
      .fill("463380");
    await expect(
      p.getByRole("button", { name: "Search", exact: true }),
    ).toBeEnabled({ timeout: 120000 });
    await p.getByRole("button", { name: "Search", exact: true }).click();
    await expect(p.locator("tbody")).toContainText("463380", {
      timeout: 120000,
    });
    await shot("catalogue");
    await go("Deliveries");
    await shot("deliveries");
    await go("Invoices");
    await shot("invoices");
    await p.getByRole("button", { name: "View", exact: true }).first().click();
    await expect(
      p.getByRole("dialog", { name: "Invoice", exact: true }),
    ).toContainText("Sample account invoice");
    await shot("invoice-view");
    await p.getByRole("button", { name: "Close invoice", exact: true }).click();
    await go("Settings");
    await shot("settings-rules");
    for (const [label, id] of [
      ["Team", "team"],
      ["Connected assistants", "connected"],
      ["Kitchen profile", "kitchen"],
    ]) {
      await p.getByRole("link", { name: label, exact: true }).click();
      await shot("settings-" + id);
    }
    await p
      .getByRole("button", { name: "Account events", exact: true })
      .click();
    await shot("bell");
    await p
      .getByRole("button", { name: "Account events", exact: true })
      .click();
    const after = await (await ctx.request.get(base + "/api/account")).json();
    expect(
      JSON.stringify(
        after.orders.map((o) => [
          o.order_number,
          o.total,
          o.placed_at,
          o.status,
        ]),
      ),
    ).toBe(baseline);
    await ctx.close();
  }
  expect(report.console_errors).toEqual([]);
  report.verdict = "PASS";
  fs.writeFileSync(
    "artifacts/e2e/job03/taste-gate.json",
    JSON.stringify(report, null, 2),
  );
  console.log(
    JSON.stringify({
      verdict: report.verdict,
      screenshots: report.screenshots.length,
      aurora: report.aurora,
      console_errors: report.console_errors,
    }),
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
