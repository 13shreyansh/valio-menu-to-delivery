const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const f = JSON.parse(fs.readFileSync("artifacts/ui-local.json"));
const code = fs.readFileSync("public/app.js", "utf8");
function setup() {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(e.message));
  const dom = new JSDOM(fs.readFileSync("public/index.html", "utf8"), {
    url: "https://valio-menu-to-delivery.vercel.app",
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const w = dom.window;
  w.scrollTo = () => {};
  w.matchMedia = () => ({ matches: false });
  w.fetch = async () => ({ ok: true, json: async () => ({}) });
  w.eval(
    code +
      `;window.hooks={render,state:S,esc,orderPage,start,rulesView,checklistLabel,fakeRecording:()=>{S.listening=true;recorder={stop:()=>{window.micStopped=true}};stream={getTracks:()=>[{stop:()=>{window.trackStopped=true}}]}}};`,
  );
  return { dom, w, errors };
}
const rules = {
  weekly_limit: 800,
  growth_limit: 200,
  over_limit: "ask",
  ask_swap: true,
  same_allergens: true,
  allergens: ["nuts", "peanuts"],
  monthly_limit: 6000,
  changed_by: "Sanna",
  changed_at: "2026-11-02",
};
function account(w) {
  const o = structuredClone(f.wedding);
  o.draft_id = "1".repeat(32);
  o.rules = rules;
  o.status = "draft";
  o.baseline_total = f.initial.total;
  o.request = "Wedding Saturday 120 guests";
  o.reading = {
    covers: 120,
    dishes: [{ recipe: "salmon" }, { recipe: "tart" }],
  };
  const s = w.hooks.state;
  Object.assign(s, {
    order: o,
    account: {
      rules,
      team: [],
      bookings: o.kitchen.bookings,
      recipes: o.recipes,
      stock: o.stock,
      orders: [],
      events: [],
    },
    path: "/orders/week-47",
  });
  return o;
}
test("signed-out screen has no password or story controls", () => {
  const { dom, w } = setup();
  assert.equal(w.document.querySelectorAll("[type=password]").length, 0);
  assert.ok(
    w.document.body.textContent.includes("Try the demo account (Hotel Aurora)"),
  );
  assert.ok(!/Play the story|Stop story/.test(w.document.body.textContent));
  dom.window.close();
});
test("untrusted request and catalogue names are escaped", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  w.hooks.state.request = "<img src=x onerror=alert(1)>";
  w.hooks.render();
  assert.equal(w.document.querySelectorAll("img").length, 0);
  assert.ok(
    w.document.querySelector(".request-block").textContent.includes("<img"),
  );
  dom.window.close();
});
test("Place order exists only in the footer and is disabled for pending OKs", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.render();
  assert.equal(w.document.querySelectorAll("[data-action=place]").length, 1);
  assert.equal(
    w.document.querySelector("[data-action=place]").closest(".footer-bar") !==
      null,
    true,
  );
  assert.equal(w.document.querySelector("[data-action=place]").disabled, true);
  dom.window.close();
});
test("approved and reopened rows show the actual approval state", () => {
  const { dom, w } = setup();
  const o = account(w);
  o.checks[0].approved = true;
  o.checks[0].approved_at = "21:14";
  o.checks[1].reopened = true;
  w.hooks.render();
  assert.ok(
    w.document
      .querySelector(".approved")
      .textContent.includes("Approved by Sanna"),
  );
  assert.ok(
    w.document.body.textContent.includes(
      "You changed the quantity, so please check this again.",
    ),
  );
  dom.window.close();
});
test("receipt is readable without exposing credentials and has actual-call details", () => {
  const { dom, w } = setup();
  const o = account(w);
  o.evidence.calls = [
    {
      method: "POST",
      path: "/api/price",
      source: "Valio API",
      request: { customer: "HC-1001" },
      response: { products: [] },
      duration_ms: 27,
    },
  ];
  w.hooks.state.drawer = "receipt";
  w.hooks.render();
  assert.ok(w.document.querySelector(".receipt details"));
  assert.ok(w.document.querySelector(".receipt").textContent.includes("27 ms"));
  assert.ok(
    !/API_KEY|password/.test(w.document.querySelector(".receipt").textContent),
  );
  dom.window.close();
});
test("Settings exposes all enforced controls as normal inputs", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.path = "/settings/rules";
  w.hooks.render();
  assert.equal(w.document.querySelectorAll("[data-rule]").length, 5);
  assert.ok(
    w.document.body.textContent.includes("These rules apply to every order"),
  );
  dom.window.close();
});
test("a catalogue response preserves a query typed while the first search is loading", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.path = "/catalogue";
  let resolve;
  w.fetch = () => new Promise((r) => (resolve = r));
  const pending = w.eval("loadCatalogue()");
  const input = w.document.querySelector("#catalogue-search input");
  input.value = "463380";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  resolve({ ok: true, json: async () => ({ products: [] }) });
  await pending;
  assert.equal(
    w.document.querySelector("#catalogue-search input").value,
    "463380",
  );
  dom.window.close();
});
test("Escape stops both the recording and microphone tracks before closing Ask Valio", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  w.hooks.fakeRecording();
  w.hooks.render();
  w.document.dispatchEvent(
    new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
  );
  await new Promise((r) => setImmediate(r));
  assert.equal(w.micStopped, true);
  assert.equal(w.trackStopped, true);
  assert.equal(w.hooks.state.listening, false);
  assert.equal(w.hooks.state.drawer, null);
  dom.window.close();
});
test("company sign-in note does not leak into signed-in account screens", async () => {
  const { dom, w } = setup();
  const order = account(w);
  const acc = w.hooks.state.account;
  w.hooks.state.path = "/";
  w.hooks.render();
  w.fetch = async (url) => ({
    ok: true,
    json: async () =>
      url === "/api/account" ? acc : url === "/api/drafts" ? order : {},
  });
  w.document.querySelector("[data-action=company]").click();
  assert.equal(w.hooks.state.companyNote, true);
  w.document.querySelector("[data-action=login]").click();
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
  assert.equal(w.hooks.state.notice, "");
  assert.equal(w.hooks.state.companyNote, false);
  w.hooks.state.path = "/settings/connected-ai";
  w.hooks.render();
  assert.equal(w.document.querySelector(".status-note"), null);
  dom.window.close();
});
test("checklist labels follow the parsed delivery day and saved allergen rules", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.account.rules = {
    ...rules,
    allergens: ["nuts", "peanuts", "milk"],
  };
  assert.equal(
    w.hooks.checklistLabel(2, { date: "2026-11-18" }),
    "Checking Wednesday stock at Valio",
  );
  assert.ok(w.hooks.checklistLabel(4, {}).includes("no milk"));
  dom.window.close();
});
test("assistant drafts can be opened from the account Drafts table", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.path = "/orders";
  w.hooks.state.tab = "Drafts";
  w.hooks.state.account.drafts = [
    {
      draft_id: "a".repeat(32),
      order_number: "Week 47",
      placed_by: "Aurora Group assistant",
      placed_at: "2026-11-14T21:00:00Z",
      total: 95.55,
      products: 9,
      deliveries: [{ date: "2026-11-18" }],
      status: "Draft",
    },
  ];
  w.hooks.render();
  assert.equal(
    w.document.querySelector("a[data-open-draft]").getAttribute("href"),
    "/orders/draft-" + "a".repeat(32),
  );
  assert.ok(
    w.document
      .querySelector("tbody")
      .textContent.includes("Aurora Group assistant"),
  );
  dom.window.close();
});
test("untrusted event names are escaped in dashboard summaries and product tags", () => {
  const { dom, w } = setup();
  const o = account(w);
  o.wedding.event = "<img src=x onerror=alert(1)>";
  w.hooks.state.path = "/dashboard";
  w.hooks.render();
  assert.equal(w.document.querySelectorAll("img").length, 0);
  assert.ok(
    w.document.querySelector(".change-summary").textContent.includes("<img"),
  );
  w.hooks.state.path = "/orders/week-47";
  w.hooks.render();
  assert.equal(w.document.querySelectorAll("img").length, 0);
  dom.window.close();
});
test("unplaced assistant drafts never claim placement or within-rules approval", () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.path = "/orders";
  w.hooks.state.tab = "Drafts";
  w.hooks.state.account.drafts = [
    {
      draft_id: "a".repeat(32),
      order_number: "Week 47",
      placed_by: "Aurora Group assistant",
      placed_at: "2026-11-14T21:00:00Z",
      total: 95.55,
      deliveries: [],
      status: "Draft",
    },
  ];
  w.hooks.render();
  const text = w.document.querySelector("tbody").textContent;
  assert.ok(text.includes("Prepared by Aurora Group assistant"));
  assert.ok(!text.includes("Placed by Aurora Group assistant"));
  assert.ok(!text.includes("Within your rules"));
  dom.window.close();
});
