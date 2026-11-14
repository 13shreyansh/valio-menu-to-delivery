const { test, expect } = require("@playwright/test");
const { execFileSync } = require("child_process");
const fs = require("fs");
const base =
  process.env.BASE_URL || "https://valio-menu-to-delivery.vercel.app";
test.setTimeout(360000);
const shot = async (p, name) => {
  await p.screenshot({ path: `artifacts/e2e/${name}.png`, fullPage: false });
};
async function go(p, label) {
  if (
    await p.getByRole("button", { name: "Open menu", exact: true }).isVisible()
  )
    await p.getByRole("button", { name: "Open menu", exact: true }).click();
  await p
    .locator(".sidebar")
    .getByRole("link", { name: label, exact: true })
    .click();
}
for (const [name, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["phone", { width: 390, height: 844 }],
])
  test(`${name}: real wedding ordering flow`, async ({ browser }) => {
    const kitchen = require("../scripts/test_kitchen.cjs")();
    const ctx = await browser.newContext({
      viewport,
      extraHTTPHeaders: kitchen.headers,
    });
    const p = await ctx.newPage();
    const errors = [];
    p.on("pageerror", (e) => errors.push(e.message));
    p.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await p.goto(base + "/");
    await shot(p, `${name}-start`);
    await p
      .getByRole("button", {
        name: "Continue with company account",
        exact: true,
      })
      .click();
    await expect(
      p.getByText("Company sign-in is set up by your Valio contact"),
    ).toBeVisible();
    await p
      .getByRole("button", {
        name: "Try the demo account (Hotel Aurora)",
        exact: true,
      })
      .click();
    await expect(
      p.getByRole("button", { name: "Review order", exact: true }),
    ).toBeVisible({ timeout: 240000 });
    await expect(p.locator(".order-card")).toContainText("46 products");
    await shot(p, `${name}-dashboard-default`);
    await p.getByRole("button", { name: "Ask Valio", exact: true }).click();
    await p
      .locator("#ask-input")
      .fill(
        "Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.",
      );
    await p.getByRole("button", { name: "Send", exact: true }).click();
    await expect(p.locator(".checklist-row").first()).toBeVisible();
    if (name === "desktop") {
      await expect(p.locator('[data-stage="1"]')).toBeVisible({
        timeout: 120000,
      });
      await shot(p, `${name}-dashboard-working`);
    }
    await expect(p.locator(".ask-result")).toBeVisible({ timeout: 240000 });
    await expect(p.locator(".ask-result")).toContainText(
      "3 things need your OK",
    );
    await shot(p, `${name}-ask-after-send`);
    await p
      .getByRole("button", { name: "Close Ask Valio", exact: true })
      .click();
    await expect(p.locator(".order-card")).toContainText("needs 3 OKs");
    await shot(p, `${name}-dashboard-after`);
    await p.getByRole("button", { name: "Review order", exact: true }).click();
    await expect(p.locator(".approval")).toHaveCount(3);
    await expect(
      p.getByRole("button", { name: "Place order", exact: true }),
    ).toBeDisabled();
    if (viewport.width === 390) {
      const bounds = await p
        .locator(".order-table tbody tr")
        .first()
        .evaluate((row) => {
          const link = row
            .querySelector('[data-action="why"]')
            .getBoundingClientRect();
          const box = row.getBoundingClientRect();
          return {
            left: link.left,
            right: link.right,
            rowLeft: box.left,
            rowRight: box.right,
          };
        });
      expect(bounds.left).toBeGreaterThanOrEqual(bounds.rowLeft);
      expect(bounds.right).toBeLessThanOrEqual(bounds.rowRight);
      expect(bounds.right).toBeLessThanOrEqual(viewport.width);
    }
    await shot(p, `${name}-order-three-checks`);
    for (const id of ["swap", "pack", "budget"]) {
      await p
        .locator(`[data-check="${id}"] button[data-action="approve"]`)
        .click();
      await expect(p.locator(`[data-check="${id}"]`)).toHaveClass(/approved/, {
        timeout: 90000,
      });
    }
    await expect(
      p.getByRole("button", { name: "Place order", exact: true }),
    ).toBeEnabled();
    for (const [id, title] of [
      ["swap", "Swap salmon for"],
      ["pack", "Buy cream as"],
      ["budget", "weekly limit"],
    ]) {
      await expect(p.locator(`[data-check="${id}"]`)).toContainText(title);
      await expect(p.locator(`[data-check="${id}"]`)).toContainText(
        "approved by Sanna",
      );
    }
    await shot(p, `${name}-approved-titles`);
    // Increasing cream affects both its pack approval and the weekly spend approval.
    const more = p
      .locator('tr[data-row="2026-11-20-cream"] button[data-action="qty"]')
      .last();
    await more.click();
    await expect(p.locator('[data-check="pack"]')).not.toHaveClass(/approved/, {
      timeout: 90000,
    });
    await expect(
      p
        .getByText("You changed the quantity, so please check this again.")
        .first(),
    ).toBeVisible();
    await expect(
      p.getByRole("button", { name: "Place order", exact: true }),
    ).toBeDisabled();
    await p.evaluate(() => window.scrollTo(0, 0));
    await shot(p, `${name}-approval-reopened`);
    for (const id of ["pack", "budget"]) {
      await p
        .locator(`[data-check="${id}"] button[data-action="approve"]`)
        .click();
      await expect(p.locator(`[data-check="${id}"]`)).toHaveClass(/approved/, {
        timeout: 90000,
      });
    }
    await p
      .locator('tr[data-row="2026-11-20-cream"] button[data-action="why"]')
      .click();
    await expect(
      p.getByRole("dialog", { name: "Why this product" }),
    ).toContainText("120 guests");
    await shot(p, `${name}-why`);
    await p
      .getByRole("button", { name: "Close explanation", exact: true })
      .click();
    await p
      .getByRole("button", { name: "How this was decided", exact: true })
      .click();
    await expect(p.locator(".receipt")).toContainText("Valio product data");
    await p.locator(".receipt details").first().locator("summary").click();
    await expect(p.locator(".receipt pre").first()).toBeVisible();
    await shot(p, `${name}-receipt`);
    await p.getByRole("button", { name: "Close receipt", exact: true }).click();
    await go(p, "Settings");
    await expect(
      p.getByRole("spinbutton", { name: "Weekly limit", exact: true }),
    ).toHaveValue("1500");
    await shot(p, `${name}-settings-rules`);
    await p
      .getByRole("link", { name: "Connected assistants", exact: true })
      .click();
    await expect(
      p.getByRole("textbox", { name: "MCP address", exact: true }),
    ).toHaveValue("https://valio-menu-to-delivery.vercel.app/mcp/");
    await shot(p, `${name}-connected-assistants`);
    await go(p, "Dashboard");
    await p.getByRole("button", { name: "Review order", exact: true }).click();
    await p.getByRole("button", { name: "Place order", exact: true }).click();
    await expect(
      p.getByRole("heading", { name: "Order sent to Valio", exact: true }),
    ).toBeVisible({ timeout: 120000 });
    await expect(
      p.getByText("Demo account: no real order was placed.", { exact: true }),
    ).toBeVisible();
    await shot(p, `${name}-confirmation`);
    await p.getByRole("button", { name: "View orders", exact: true }).click();
    await expect(p.locator("main table tbody tr").first()).toContainText(
      "Sanna Virtanen",
    );
    await shot(p, `${name}-orders`);
    if (name === "desktop") {
      const raw = execFileSync(
        ".venv/bin/python",
        ["scripts/mcp_client.py", base],
        {
          encoding: "utf8",
          timeout: 240000,
          env: { ...process.env, VALIO_TEST_RUN: kitchen.run },
        },
      );
      const report = JSON.parse(raw.trim());
      fs.writeFileSync(
        "artifacts/e2e/mcp-client.json",
        JSON.stringify(report, null, 2),
      );
      await go(p, "Dashboard");
      await go(p, "Orders");
      const row = p.locator("tr").filter({ hasText: report.order_number });
      await expect(row).toContainText("Placed by Aurora Group assistant", {
        timeout: 60000,
      });
      await expect(row).toContainText("Within your rules");
      await shot(p, "desktop-orders-after-mcp");
      await p
        .getByRole("button", { name: "Account events", exact: true })
        .click();
      await expect(p.locator(".events")).toContainText(report.order_number);
      await shot(p, "desktop-bell-after-mcp");
      await p
        .getByRole("button", { name: "Account events", exact: true })
        .click();
      await go(p, "Dashboard");
      await expect(p.locator(".recent")).toContainText(report.order_number);
      await shot(p, "desktop-dashboard-after-mcp");
    }
    for (const label of ["Catalogue", "Deliveries", "Invoices"]) {
      await go(p, label);
      if (label === "Catalogue") {
        await p
          .getByRole("textbox", {
            name: "Search products or codes",
            exact: true,
          })
          .fill("463380");
        await p.getByRole("button", { name: "Search", exact: true }).click();
        await expect(p.locator("tbody")).toContainText("463380", {
          timeout: 120000,
        });
      }
      await expect(p.locator("main table")).toBeVisible();
      await shot(p, `${name}-${label.toLowerCase()}`);
    }
    expect(errors).toEqual([]);
    fs.writeFileSync(
      `artifacts/e2e/${name}-console.json`,
      JSON.stringify(errors),
    );
    await ctx.close();
  });
