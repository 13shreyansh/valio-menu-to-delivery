// These tests execute DOM interactions in JSDOM. They do not assert browser layout or microphone quality.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { JSDOM, VirtualConsole } = require("jsdom");
const fixture = JSON.parse(fs.readFileSync("artifacts/ui-local.json", "utf8"));
const script = fs.readFileSync("public/app.js", "utf8");
const html = fs.readFileSync("public/index.html", "utf8");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function setup(handler) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => errors.push(e));
  const dom = new JSDOM(html, {
    url: "https://valio-menu-to-delivery.vercel.app",
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const w = dom.window;
  w.matchMedia = () => ({ matches: true });
  w.HTMLElement.prototype.scrollIntoView = () => {};
  w.structuredClone = structuredClone;
  w.fetch = async (url, opts) => ({
    ok: true,
    json: async () =>
      handler
        ? await handler(url, opts?.body ? JSON.parse(opts.body) : null)
        : structuredClone(fixture.initial),
  });
  w.eval(
    script +
      `;window.testHooks={render,showDecisions,setPhoto:(value,src)=>{photo=value;photoSrc=src;renderPhoto();}};`,
  );
  await wait(10);
  return { w, dom, errors };
}
function assertWorking(w) {
  for (const row of w.document.querySelectorAll(".order-row")) {
    const qty = row.querySelector(".qty").textContent;
    const end = row.querySelector(".working b").textContent;
    assert.ok(end.startsWith(qty + " ×"), `${qty} != ${end}`);
  }
}
test("loads directly to a real sheet and every displayed quantity ends its working", async () => {
  const { w, dom, errors } = await setup();
  try {
    assert.equal(
      w.document.querySelector("h1").textContent,
      "Next week's order is ready",
    );
    assert.equal(
      w.document.querySelectorAll(".order-row").length,
      fixture.initial.rows.length,
    );
    assert.equal(w.document.querySelector("#place").textContent, "Place order");
    assertWorking(w);
    assert.deepEqual(errors, []);
  } finally {
    dom.window.close();
  }
});
test("typed wedding updates the sheet and locks Place order for the checks", async () => {
  let calls = [];
  const { w, dom, errors } = await setup((url, body) => {
    calls.push([url, body]);
    return url.endsWith("/tell")
      ? {
          ...fixture.wedding,
          reading: {
            status: "readable",
            transcript: "Wedding Saturday, 120 guests, salmon and lemon tart",
          },
        }
      : fixture.initial;
  });
  try {
    w.document.querySelector("#keyboard").click();
    w.document.querySelector("#tell-text").value =
      "Wedding Saturday, 120 guests, salmon and lemon tart";
    w.document
      .querySelector("#tell-form")
      .dispatchEvent(new w.Event("submit", { cancelable: true }));
    await wait(20);
    assert.equal(
      w.document.querySelector("#place").textContent,
      "3 things to check first",
    );
    assert.equal(w.document.querySelectorAll("[data-approve]").length, 3);
    assertWorking(w);
    assert.deepEqual(errors, []);
  } finally {
    dom.window.close();
  }
});
test("one cream increment reopens pack and weekly budget approval", async () => {
  const { w, dom } = await setup((url, body) =>
    url.endsWith("/change") ? fixture.reopened : fixture.initial,
  );
  try {
    w.testHooks.render(fixture.approved);
    w.document
      .querySelector('[data-id="2026-11-20-cream"][data-step="1"]')
      .click();
    await wait(20);
    assert.equal(w.document.querySelectorAll(".check.reopened").length, 2);
    assert.ok(w.document.querySelector("#place").classList.contains("locked"));
    assertWorking(w);
  } finally {
    dom.window.close();
  }
});
test("blank photo has what-we-saw recovery and cannot update order", async () => {
  const { w, dom } = await setup();
  try {
    w.bad = {
      status: "unreadable",
      transcript: "",
      dishes: [],
      read: [],
      reason: "Couldn't read the full menu.",
    };
    w.testHooks.setPhoto(w.bad, "/whiteboards/blank.jpg");
    assert.equal(w.document.querySelector("#apply-photo").disabled, true);
    assert.match(
      w.document.querySelector("#photo-panel").textContent,
      /No legible words/,
    );
    assert.equal(w.document.querySelector("#place").textContent, "Place order");
  } finally {
    dom.window.close();
  }
});
test("uncertain legible photo exposes in-place correction and explicit review", async () => {
  const { w, dom } = await setup();
  try {
    w.reading = {
      ...fixture.photo,
      status: "uncertain",
      uncertain: ["siika?"],
    };
    w.testHooks.setPhoto(w.reading, "/whiteboards/menu-1.jpg");
    assert.equal(w.document.querySelectorAll("[data-dish]").length, 3);
    assert.equal(w.document.querySelector("#apply-photo").disabled, true);
    w.document.querySelector("#confirm-words").click();
    assert.equal(w.document.querySelector("#apply-photo").disabled, false);
  } finally {
    dom.window.close();
  }
});
test("technical receipt takes an extra expansion and removed-menu products cannot be restored with a stepper", async () => {
  const { w, dom } = await setup();
  try {
    w.testHooks.render(fixture.final);
    w.testHooks.showDecisions();
    const pre = w.document.querySelector("#decision-panel pre");
    assert.equal(
      pre.closest("details").parentElement.closest("details").tagName,
      "DETAILS",
    );
    for (const row of w.document.querySelectorAll(".order-row.removed")) {
      assert.equal(row.querySelector('[data-step="1"]').disabled, true);
      assert.ok(!row.querySelector("[data-restore]"));
    }
  } finally {
    dom.window.close();
  }
});
test("stopping during an in-flight story response prevents its late render", async () => {
  let resolveWedding,
    called = false;
  const { w, dom } = await setup((url) => {
    if (url.endsWith("/story-reading"))
      return { ready: true, wedding_token: "test", photo: fixture.photo };
    if (url.endsWith("/story-wedding")) {
      called = true;
      return new Promise((r) => (resolveWedding = r));
    }
    return fixture.initial;
  });
  try {
    const native = w.setTimeout;
    w.setTimeout = (fn, ms) => native(fn, Math.min(ms, 1));
    w.document.querySelector("#play").click();
    for (let i = 0; i < 100 && !called; i++) await wait(2);
    assert.ok(called);
    w.document.querySelector("#stop-story").click();
    resolveWedding(fixture.wedding);
    await wait(20);
    assert.equal(w.document.querySelector("#place").textContent, "Place order");
    assert.equal(w.document.querySelector("#result-summary").hidden, true);
    assert.ok(
      !w.document.querySelector("#notice").textContent.includes("STOP_STORY"),
    );
  } finally {
    dom.window.close();
  }
});

test("the entire recorded story reaches confirmation through its controls", async () => {
  let afterPhoto = false,
    approveCounts = {};
  const { w, dom, errors } = await setup((url, body) => {
    if (url.endsWith("/story-reading"))
      return {
        ready: true,
        wedding_token: "test",
        read_token: "photo-test",
        photo: fixture.photo,
      };
    if (url.endsWith("/story-wedding")) return fixture.wedding;
    if (url.endsWith("/photo/apply")) {
      afterPhoto = true;
      return fixture.final;
    }
    if (url.endsWith("/change")) {
      if (body.action === "quantity") return fixture.reopened;
      if (body.action === "place") return fixture.confirmed;
      if (body.action === "approve") {
        approveCounts[body.value] = (approveCounts[body.value] || 0) + 1;
        return afterPhoto
          ? fixture.final_approved
          : approveCounts[body.value] > 1
            ? fixture.approved
            : fixture.acks[body.value];
      }
    }
    return fixture.initial;
  });
  try {
    const native = w.setTimeout;
    w.setTimeout = (fn, ms) => native(fn, Math.min(ms, 1));
    w.document.querySelector("#play").click();
    for (
      let i = 0;
      i < 200 && w.document.querySelector("#confirmation").hidden;
      i++
    )
      await wait(2);
    assert.equal(w.document.querySelector("#confirmation").hidden, false);
    assert.match(
      w.document.querySelector("#confirmation").textContent,
      /Order placed/,
    );
    assert.match(
      w.document.querySelector("#confirmation").textContent,
      /Nothing ships/,
    );
    assert.equal(w.document.querySelector("#layout").hidden, true);
    assert.deepEqual(errors, []);
  } finally {
    dom.window.close();
  }
});
