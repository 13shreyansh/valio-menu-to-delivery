const { chromium, expect } = require("@playwright/test");
const fs = require("node:fs");
(async () => {
  const base = process.argv[2] || "https://valio-menu-to-delivery.vercel.app";
  const b = await chromium.launch({ headless: true });
  const kitchen = require("./test_kitchen.cjs")();
  const ctx = await b.newContext({
    extraHTTPHeaders: kitchen.headers,
    viewport: { width: 1440, height: 900 },
  });
  const p = await ctx.newPage();
  p.setDefaultTimeout(30000);
  const report = {};
  let original;
  try {
    await p.goto(base);
    await p
      .getByRole("button", {
        name: "Try the demo account (Hotel Aurora)",
        exact: true,
      })
      .click();
    await p
      .getByRole("button", { name: "Review order", exact: true })
      .waitFor({ timeout: 120000 });
    original = (await (await ctx.request.get(base + "/api/account")).json())
      .rules;
    await p
      .locator(".sidebar")
      .getByRole("link", { name: "Settings", exact: true })
      .click();
    const save = p.waitForResponse(
      (r) => r.url().endsWith("/api/rules") && r.request().method() === "POST",
    );
    await p
      .getByRole("spinbutton", { name: "Weekly limit", exact: true })
      .fill("100");
    await p
      .getByRole("spinbutton", { name: "Weekly limit", exact: true })
      .press("Tab");
    expect((await save).status()).toBe(200);
    const block = p.waitForResponse(
      (r) => r.url().endsWith("/api/rules") && r.request().method() === "POST",
    );
    await p
      .getByRole("combobox", { name: "When an order goes over", exact: true })
      .selectOption("block");
    expect((await block).status()).toBe(200);
    await p.reload();
    await expect(
      p.getByRole("spinbutton", { name: "Weekly limit", exact: true }),
    ).toHaveValue("100", { timeout: 120000 });
    await expect(
      p.getByRole("combobox", { name: "When an order goes over", exact: true }),
    ).toHaveValue("block", { timeout: 120000 });
    report.persisted_rules = "passed";
    await p
      .locator(".sidebar")
      .getByRole("link", { name: "Dashboard", exact: true })
      .click();
    await p.getByRole("button", { name: "Review order", exact: true }).click();
    await expect(
      p.getByRole("button", { name: "Place order", exact: true }),
    ).toBeDisabled();
    await expect(p.locator("[data-check=budget]")).toContainText(
      "does not allow this order",
    );
    await expect(
      p.locator("[data-check=budget] [data-action=approve]"),
    ).toHaveCount(0);
    await p.screenshot({ path: "artifacts/controls/web-budget-block.png" });
    report.web_budget_block = "passed";
    const headers = {
      Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": "2025-11-25",
    };
    const initialize = await ctx.request.post(base + "/mcp/", {
      headers,
      data: {
        jsonrpc: "2.0",
        id: 0,
        method: "initialize",
        params: {
          protocolVersion: "2025-11-25",
          capabilities: {},
          clientInfo: { name: "ordering-rule-verification", version: "1" },
        },
      },
    });
    expect(initialize.status()).toBe(200);
    const rpc = async (name, args) => {
      const r = await ctx.request.post(base + "/mcp/", {
        headers,
        data: {
          jsonrpc: "2.0",
          id: 1,
          method: "tools/call",
          params: { name, arguments: args },
        },
      });
      expect(r.status()).toBe(200);
      return (await r.json()).result;
    };
    const raw = await rpc("prepare_order", {
      request: "Breakfast for 400 for Wednesday",
    });
    const o =
      raw.structuredContent ||
      JSON.parse(raw.content.find((c) => c.type === "text").text);
    expect(o.can_place).toBe(false);
    const result = await rpc("place_order", { draft_id: o.draft_id });
    expect(result.isError).toBe(true);
    expect(result.content.map((c) => c.text).join(" ")).toMatch(
      /chef to review/,
    );
    report.mcp_budget_block = "passed";
    report.blocked_draft = o.draft_id;
    await p
      .locator(".sidebar")
      .getByRole("link", { name: "Orders", exact: true })
      .click();
    await p.getByRole("button", { name: "Drafts", exact: true }).click();
    const row = p.locator(`tr[data-open-draft="${o.draft_id}"]`);
    await expect(row).toContainText("Prepared by Aurora Group assistant");
    await row.locator("a").click();
    await expect(
      p.getByRole("button", { name: "Place order", exact: true }),
    ).toBeDisabled();
    report.assistant_review_draft = "passed";
    await p.screenshot({ path: "artifacts/controls/assistant-draft.png" });
    // Restore through the same account API; the following catalogue check uses the original rules.
    expect(
      (
        await ctx.request.post(base + "/api/rules", { data: original })
      ).status(),
    ).toBe(200);
    const newDraft = await (
      await ctx.request.post(base + "/api/drafts", { data: {} })
    ).json();
    await p.evaluate(
      (id) => localStorage.setItem("aurora-draft", id),
      newDraft.draft_id,
    );
    await p.goto(base + "/catalogue");
    await p
      .getByRole("textbox", { name: "Search products or codes", exact: true })
      .fill("463380");
    await p.getByRole("button", { name: "Search", exact: true }).click();
    await expect(p.locator("tbody")).toContainText("463380", {
      timeout: 120000,
    });
    const before = newDraft.rows.find((r) => r.id === "2026-11-20-milk").units;
    await p.getByRole("button", { name: "Add to order", exact: true }).click();
    await expect(
      p.getByText("Added to next week’s order.", { exact: true }),
    ).toBeVisible({ timeout: 60000 });
    const added = await (
      await ctx.request.get(base + "/api/drafts/" + newDraft.draft_id)
    ).json();
    expect(added.rows.find((r) => r.id === "2026-11-20-milk").units).toBe(
      before + 1,
    );
    report.catalogue_add = "passed";
    await p
      .locator(".sidebar")
      .getByRole("link", { name: "Invoices", exact: true })
      .click();
    await expect(p.locator("main table")).toBeVisible();
    await expect(p.locator("main")).toContainText("No orders in this view.");
    report.isolated_invoices = "passed (new test kitchen has no past invoices)";
    console.log(JSON.stringify(report, null, 2));
  } catch (e) {
    report.error = e.message;
    await p.screenshot({ path: "artifacts/controls/failure.png" });
    throw e;
  } finally {
    if (original)
      await ctx.request.post(base + "/api/rules", { data: original });
    fs.writeFileSync(
      "artifacts/controls/results.json",
      JSON.stringify(report, null, 2),
    );
    await b.close();
  }
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
