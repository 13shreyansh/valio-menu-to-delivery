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
      `;window.hooks={render,state:S,esc,orderPage,start,rulesView,checklistLabel,microphone,saveRule,flushRules:()=>ruleQueue,fakeRecording:()=>{S.listening=true;recordingSession={recorder:{stop:()=>{window.micStopped=true}},stream:{getTracks:()=>[{stop:()=>{window.trackStopped=true}}]}}}};`,
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
test("a recorder setup failure releases an already granted microphone and audio context", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  let stopped = 0,
    closed = 0;
  Object.defineProperty(w.navigator, "mediaDevices", {
    value: {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => stopped++ }],
      }),
    },
  });
  w.AudioContext = class {
    constructor() {
      this.state = "running";
    }
    createAnalyser() {
      throw Error("Injected analyser failure");
    }
    close() {
      closed++;
      return Promise.resolve();
    }
  };
  await w.hooks.microphone();
  assert.equal(stopped, 1);
  assert.equal(closed, 1);
  assert.equal(w.hooks.state.listening, false);
  assert.equal(w.hooks.state.micStarting, false);
  assert.ok(w.hooks.state.error.includes("Recording could not start"));
  dom.window.close();
});
test("a new recording cannot start while the previous recording is being transcribed", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  let created = 0,
    stopped = 0,
    closed = 0,
    resolveTranscription;
  Object.defineProperty(w.navigator, "mediaDevices", {
    value: {
      getUserMedia: async () => ({
        getTracks: () => [{ stop: () => stopped++ }],
      }),
    },
  });
  w.AudioContext = class {
    constructor() {
      this.state = "running";
    }
    createAnalyser() {
      return {
        fftSize: 0,
        frequencyBinCount: 4,
        getByteFrequencyData: (a) => a.fill(2),
      };
    }
    createMediaStreamSource() {
      return { connect: () => {} };
    }
    close() {
      closed++;
      return Promise.resolve();
    }
  };
  w.MediaRecorder = class {
    constructor() {
      created++;
      this.mimeType = "audio/webm";
      this.state = "inactive";
    }
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable({
        data: new w.Blob(["audio"], { type: "audio/webm" }),
      });
      this.onstop();
    }
  };
  w.fetch = () => new Promise((resolve) => (resolveTranscription = resolve));
  await w.hooks.microphone();
  assert.equal(w.hooks.state.listening, true);
  await w.hooks.microphone();
  assert.equal(w.hooks.state.transcribing, true);
  await w.hooks.microphone();
  assert.equal(created, 1);
  for (let i = 0; i < 10 && !resolveTranscription; i++)
    await new Promise((r) => setImmediate(r));
  resolveTranscription({
    ok: true,
    json: async () => ({ transcript: "Breakfast for 40 Wednesday" }),
  });
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
  assert.equal(stopped, 1);
  assert.equal(closed, 1);
  assert.equal(w.hooks.state.transcribing, false);
  assert.equal(w.hooks.state.input, "Breakfast for 40 Wednesday");
  dom.window.close();
});
test("successive rule edits queue instead of silently dropping the later control change", async () => {
  const { dom, w } = setup();
  const o = account(w);
  w.hooks.state.path = "/settings/rules";
  w.hooks.render();
  let firstResolve;
  const calls = [];
  let saved = { ...rules };
  w.fetch = async (url, opts) => {
    if (url === "/api/rules") {
      const change = JSON.parse(opts.body);
      calls.push(change);
      if (calls.length === 1)
        return new Promise(
          (resolve) =>
            (firstResolve = () => {
              saved = { ...saved, ...change };
              resolve({ ok: true, json: async () => saved });
            }),
        );
      saved = { ...saved, ...change };
      return { ok: true, json: async () => saved };
    }
    return { ok: true, json: async () => o };
  };
  const a = w.hooks.saveRule("weekly_limit", 100);
  const b = w.hooks.saveRule("over_limit", "block");
  for (let i = 0; i < 3; i++) await new Promise((r) => setImmediate(r));
  firstResolve();
  await b;
  assert.deepEqual(calls, [{ weekly_limit: 100 }, { over_limit: "block" }]);
  assert.equal(w.hooks.state.account.rules.weekly_limit, 100);
  assert.equal(
    w.document.querySelector("[data-rule=over_limit]").value,
    "block",
  );
  assert.equal(w.hooks.state.rulesSaving, false);
  dom.window.close();
});
test("closing Ask Valio while microphone permission is pending stops a later granted stream", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  let grant,
    stopped = 0;
  Object.defineProperty(w.navigator, "mediaDevices", {
    value: { getUserMedia: () => new Promise((r) => (grant = r)) },
  });
  const pending = w.hooks.microphone();
  assert.equal(w.hooks.state.micStarting, true);
  w.document.dispatchEvent(
    new w.KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
  );
  await new Promise((r) => setImmediate(r));
  grant({ getTracks: () => [{ stop: () => stopped++ }] });
  await pending;
  assert.equal(stopped, 1);
  assert.equal(w.hooks.state.listening, false);
  assert.equal(w.hooks.state.drawer, null);
  dom.window.close();
});
test("the settings saving guard remains active for a second edit arriving during draft refresh", async () => {
  const { dom, w } = setup();
  const o = account(w);
  let finishRefresh, finishSecond;
  let requests = 0;
  w.fetch = async (url, opts) => {
    if (url === "/api/rules") {
      requests++;
      if (requests === 1)
        return {
          ok: true,
          json: async () => ({ ...rules, weekly_limit: 100 }),
        };
      return new Promise(
        (r) =>
          (finishSecond = () =>
            r({
              ok: true,
              json: async () => ({
                ...rules,
                weekly_limit: 100,
                over_limit: "block",
              }),
            })),
      );
    }
    if (!finishRefresh)
      return new Promise(
        (r) => (finishRefresh = () => r({ ok: true, json: async () => o })),
      );
    return { ok: true, json: async () => o };
  };
  w.hooks.saveRule("weekly_limit", 100);
  for (let i = 0; i < 5 && !finishRefresh; i++)
    await new Promise((r) => setImmediate(r));
  const second = w.hooks.saveRule("over_limit", "block");
  finishRefresh();
  for (let i = 0; i < 5 && !finishSecond; i++)
    await new Promise((r) => setImmediate(r));
  assert.equal(w.hooks.state.rulesSaving, true);
  finishSecond();
  await second;
  assert.equal(w.hooks.state.rulesSaving, false);
  dom.window.close();
});
test("an automatic recorder stop clears Listening and completes the transcript", async () => {
  const { dom, w } = setup();
  account(w);
  w.hooks.state.drawer = "ask";
  let rec;
  Object.defineProperty(w.navigator, "mediaDevices", {
    value: {
      getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }),
    },
  });
  w.AudioContext = class {
    constructor() {
      this.state = "running";
    }
    createAnalyser() {
      return { frequencyBinCount: 4, getByteFrequencyData: (a) => a.fill(0) };
    }
    createMediaStreamSource() {
      return { connect: () => {} };
    }
    close() {
      return Promise.resolve();
    }
  };
  w.MediaRecorder = class {
    constructor() {
      rec = this;
      this.mimeType = "audio/webm";
    }
    start() {}
    stop() {}
  };
  w.fetch = async () => ({
    ok: true,
    json: async () => ({ transcript: "Breakfast for40 Wednesday" }),
  });
  await w.hooks.microphone();
  rec.ondataavailable({ data: new w.Blob(["audio"], { type: "audio/webm" }) });
  const stopped = rec.onstop();
  assert.equal(w.hooks.state.listening, false);
  assert.equal(w.hooks.state.transcribing, true);
  await stopped;
  assert.equal(w.hooks.state.transcribing, false);
  assert.equal(w.hooks.state.input, "Breakfast for40 Wednesday");
  dom.window.close();
});
test("a rejected catalogue addition never displays a success notice", async () => {
  const { dom, w } = setup();
  account(w);
  Object.assign(w.hooks.state, {
    path: "/catalogue",
    notice: "Added to next week’s order.",
    catalogueLoaded: true,
    catalogue: [
      {
        id: "X",
        name: "Product",
        pack: 1,
        pack_dim: "l",
        unit_price: 1,
        comparison_price: 1,
        availability: { available_date: "2026-11-20" },
        allowed: true,
      },
    ],
  });
  w.fetch = async () => ({
    ok: false,
    json: async () => ({ error: "Not enough stock" }),
  });
  w.hooks.render();
  w.document.querySelector("[data-action=add]").click();
  for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r));
  assert.ok(
    w.document.querySelector(".error").textContent.includes("Not enough stock"),
  );
  assert.equal(w.document.querySelector(".status-note"), null);
  dom.window.close();
});
test("a photo event name with its weekday does not repeat the day in summaries", () => {
  const { dom, w } = setup();
  const o = account(w);
  o.wedding.event = "Saturday Wedding";
  w.hooks.state.path = "/dashboard";
  w.hooks.render();
  const text = w.document.querySelector(".change-summary").textContent;
  assert.ok(text.includes("Saturday wedding"));
  assert.ok(!/Saturday saturday/i.test(text));
  dom.window.close();
});
