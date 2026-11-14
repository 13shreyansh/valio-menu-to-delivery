"use strict";
const $ = (s) => document.querySelector(s),
  $$ = (s) => [...document.querySelectorAll(s)];
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (n) =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" }).format(
    n,
  );
const n = (x) => Number(x.toFixed(3)).toLocaleString("en-GB");
const paths = {
  mic: "M12 19v3m-4 0h8M5 10v2a7 7 0 0 0 14 0v-2M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z",
  camera:
    "M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3ZM16 13a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  keyboard:
    "M3 5h18v14H3zM7 9h.01M11 9h.01M15 9h.01M18 9h.01M7 12h.01M11 12h.01M15 12h.01M18 12h.01M7 16h10",
  check: "m5 12 4 4L19 6",
  alert:
    "M12 8v5m0 3h.01M10.3 3.8 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.8a2 2 0 0 0-3.4 0Z",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  clock: "M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
};
const icon = (k) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[k] || paths.alert}"/></svg>`;
$("#mic-icon").innerHTML = icon("mic");
$("#keyboard").innerHTML = icon("keyboard");
$("#camera").innerHTML = icon("camera");
let order = null,
  busy = false,
  onlyChanges = false,
  expanded = new Set(),
  photo = null,
  readToken = null,
  photoSrc = "",
  photoReadRun = 0,
  photoReceipts = [],
  storyRun = 0,
  storyActive = false,
  recorder = null,
  audioStream = null,
  audioContext = null,
  recordingPending = false,
  listenedTokens = [],
  releaseRequested = false;
const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
function notice(message) {
  $("#notice").textContent = message;
  $("#notice").hidden = false;
}
function clearNotice() {
  $("#notice").hidden = true;
}
async function api(path, body) {
  const res = await fetch("/api/sheet" + path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok)
    throw new Error(
      data.error ||
        "Valio could not be reached. Your order has not changed. Try again.",
    );
  return data;
}
function dayName(d) {
  return new Date(d + "T12:00:00+02:00").toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Europe/Helsinki",
  });
}
function cutoff(d) {
  if (!d.cutoff)
    return '<span>Order by: not supplied</span><span class="pill attention">Check time with Valio</span>';
  let minutes = Math.floor((new Date(d.cutoff) - Date.now()) / 60000),
    time = new Date(d.cutoff)
      .toLocaleString("en-GB", {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Helsinki",
      })
      .replace(",", "");
  return `<span>Order by ${esc(time)}</span><span class="pill ${minutes < 0 ? "problem" : minutes < 180 ? "attention" : "ok"}">${icon("clock")}${minutes < 0 ? "Cut-off passed" : `${Math.floor(minutes / 60)} h ${minutes % 60} min left`}</span>`;
}
function working(r) {
  const groups = new Map();
  for (const part of r.allocations)
    groups.set(part.per_cover, (groups.get(part.per_cover) || 0) + part.covers);
  const unit = r.unit === "l" ? "ml" : "g";
  let term = [...groups]
    .map(
      ([grams, covers]) =>
        `${n(covers)}${groups.size === 1 ? (r.allocations.some((a) => a.wedding) ? " guests" : " covers") : ""} × ${n(grams)}`,
    )
    .join(" + ");
  term = groups.size
    ? `${term} ${unit}`
    : r.change === "Removed"
      ? "Removed from the menu"
      : "Added by the chef";
  return `${esc(term)} <span class="operator">=</span> ${n(r.gross)} ${esc(r.unit)}${r.stock ? ` <span class="operator">−</span> ${n(r.stock)} in stock` : ""} <span class="operator">→</span> <b>${n(r.units)} × ${n(r.pack)} ${esc(r.unit)}</b>`;
}
function detail(r) {
  return `<div class="working-detail" id="working-${r.id}" ${expanded.has(r.id) ? "" : "hidden"}>${r.allocations.map((a) => `<div class="sum-item"><span>${esc(a.dish)} · ${dayName(a.date)} · ${n(a.covers)} × ${n(a.per_cover)} ${r.unit === "l" ? "ml" : "g"}</span><strong>${n(a.amount)} ${r.unit}</strong></div>`).join("")}<div class="sum-item"><span>Recipe need</span><strong>${n(r.gross)} ${r.unit}</strong></div><div class="sum-item"><span>Minus kitchen stock and earlier pack remainder</span><strong>−${n(r.stock)} ${r.unit}</strong></div><div class="sum-item"><span>Need to buy</span><strong>${n(r.need)} ${r.unit}</strong></div><div class="sum-item"><span>Rounded up to ${n(r.pack)} ${r.unit} sales units</span><strong>${n(r.planned_units)} × ${n(r.pack)} ${r.unit}</strong></div>${r.units !== r.planned_units ? `<div class="sum-item"><span>Chef changed the quantity</span><strong>${n(r.units)} × ${n(r.pack)} ${r.unit}</strong></div>` : ""}<div class="sum-item"><span>${money(r.unit_price)} per sales unit × ${n(r.units)}</span><strong>${money(r.total)}</strong></div>${r.comparison_price ? `<div class="sum-item"><span>Valio comparison price</span><strong>${money(r.comparison_price)} / ${r.unit}</strong></div>` : ""}<p class="meta">${esc(r.pack_source)}. ${esc(r.reason)}</p><p class="meta">${r.availability.model === "Terminal" ? "Arrives via terminal. " : ""}${r.availability.closing_time ? "Cut-off supplied by Valio." : "Valio did not supply this product’s cut-off. No time has been assumed."}</p><a href="#decision-panel" data-decisions>How this was decided</a></div>`;
}
function rowHTML(r, previous, index, animate) {
  const changed =
    previous &&
    (previous.units !== r.units ||
      previous.product_id !== r.product_id ||
      previous.total !== r.total);
  let arrive = animate && (changed || !previous);
  return `<div class="row-shell${arrive ? " arrive" : ""}" style="--delay:${Math.min(index, 7) * 60}ms"><article class="order-row${r.units === 0 ? " removed" : ""}" id="row-${r.id}" data-row="${r.id}"><div class="row-main"><div class="product"><div class="product-name"><strong title="${esc(r.name)}">${esc(r.name)}</strong><span class="pack">${n(r.pack)} ${r.unit}${r.sales_unit === "KG" ? " / kg" : ""}</span></div><button class="working" data-working="${r.id}" aria-expanded="${expanded.has(r.id)}" aria-controls="working-${r.id}">${working(r)}</button>${r.change ? `<span class="change-tag">${r.change} · ${esc(r.change_reason)}</span>` : ""}${r.availability.model === "Terminal" ? '<span class="terminal">Arrives via terminal</span>' : ""}</div><div class="row-price${changed ? " roll" : ""}">${money(r.total)}</div><div class="stepper" aria-label="${esc(r.name)} sales units"><button data-step="-1" data-id="${r.id}" aria-label="Less ${esc(r.name)}" ${r.units === 0 || r.change === "Removed" ? "disabled" : ""}>${icon("minus")}</button><span class="qty${changed ? " roll" : ""}" data-quantity="${r.id}">${n(r.units)}</span><button data-step="1" data-id="${r.id}" ${r.change === "Removed" ? "disabled" : ""} aria-label="More ${esc(r.name)}">${icon("plus")}</button></div></div>${r.units === 0 ? (r.change === "Removed" ? `<button class="text-button" data-undo-menu>Undo menu</button>` : `<button class="text-button" data-restore="${r.id}">Put back</button>`) : ""}${detail(r)}</article></div>`;
}
function render(next, animate = false) {
  let old = order;
  order = next;
  const first = !old;
  clearNotice();
  if (next.place_error) notice(next.place_error);
  const byId = new Map((old?.rows || []).map((r) => [r.id, r]));
  let changedIndex = 0;
  $("#intro").textContent =
    `${new Set(next.rows.filter((r) => r.units > 0).map((r) => r.product_id)).size} products, ${next.deliveries.length} deliveries. Built from your menu, ${412 + (next.wedding?.covers || 0)} booked covers and your stock.`;
  $("#sheet").innerHTML =
    next.deliveries
      .map((d) => {
        let rows = d.rows.filter((r) => !onlyChanges || r.change);
        if (!rows.length) return "";
        return `<section class="delivery" id="delivery-${d.date}"><div class="day-band"><h2>${dayName(d.date)} delivery</h2><div class="cutoff" data-date="${d.date}">${cutoff(d)}</div></div>${rows.map((r) => rowHTML(r, byId.get(r.id), r.change ? changedIndex++ : 0, animate && !!r.change)).join("")}<div class="day-total"><span>${dayName(d.date)} subtotal</span><strong>${money(d.subtotal)}</strong></div></section>`;
      })
      .join("") ||
    '<p class="all-clear">No changed products on this sheet.</p>';
  renderChecks();
  renderCovers();
  renderBudget();
  $("#kitchen-details").innerHTML =
    `<p>${esc(next.kitchen.fixture_note)}</p><strong>Kitchen rules</strong><ul>${next.kitchen.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul><details><summary>Menu, recipes and current stock</summary>${Object.entries(
      next.recipes,
    )
      .map(
        ([key, r]) =>
          `<p><strong>${esc(r.name)}</strong><br>${Object.entries(r.ingredients)
            .map(
              ([role, g]) =>
                `${esc(role)} ${g} ${["milk", "cream", "lemon"].includes(role) ? "ml" : "g"} per cover`,
            )
            .join(" · ")}</p>`,
      )
      .join("")}<p>Kitchen stock in kg or l: ${Object.entries(next.stock)
      .map(([role, a]) => `${esc(role)} ${n(a)}`)
      .join(
        " · ",
      )}</p></details><p>Prices checked ${new Date(next.quote_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}. Prices exclude VAT.</p>`;
  $("#place").disabled = false;
  $("#place").classList.toggle("locked", !next.can_place);
  $("#place").textContent = next.pending
    ? `${next.pending} thing${next.pending === 1 ? "" : "s"} to check first`
    : "Place order";
  if (animate && old) {
    const counts = { Added: 0, More: 0, Less: 0, Removed: 0, Swapped: 0 };
    next.rows.forEach((r) => {
      let p = byId.get(r.id);
      if (
        r.change &&
        (!p || r.units !== p.units || r.product_id !== p.product_id)
      )
        counts[r.change]++;
    });
    old.rows.forEach((r) => {
      if (!next.rows.some((v) => v.id === r.id)) counts.Removed++;
    });
    $("#result-summary").hidden = false;
    $("#result-summary").innerHTML = `<span>${
      Object.entries(counts)
        .filter(([, v]) => v)
        .map(([k, v]) => `${k} ${v}`)
        .join(", ") || "Updated your menu"
    }. ${money(old.total)} → ${money(next.total)}.</span><button class="text-button" id="only-changes">${onlyChanges ? "Show full order" : "Show only what changed"}</button><button class="text-button" id="undo-wedding">Undo</button>`;
  }
  if (next.confirmation) showConfirmation();
  else {
    $("#confirmation").hidden = true;
    $("#layout").hidden = false;
    $("#dock").hidden = false;
  }
  if (first) $("#main").setAttribute("aria-busy", "false");
}
function renderChecks() {
  let cs = order.checks;
  $("#checks").innerHTML =
    `<h2>${!cs.length ? "Ready to order" : order.pending ? `${order.pending} thing${order.pending === 1 ? "" : "s"} to check` : "All checked"}</h2>${!cs.length ? `<div class="all-clear">${icon("check")}Nothing needs your OK</div>` : cs.map((c) => (c.approved ? `<div class="check approved">${icon("check")}<span>${c.kind === "swap" ? "Swap" : c.kind === "pack" ? "Larger pack" : "Budget"} OK'd ${esc(c.approved_at)}</span><button class="text-button" data-unapprove="${c.id}">Undo</button></div>` : `<div class="check${c.reopened ? " reopened" : ""}" id="check-${c.id}"><div class="check-head">${icon("alert")}<div class="check-text">${c.reopened ? `<strong class="reopen-copy">You changed ${c.kind === "budget" ? "the order" : c.kind === "pack" ? "Kuohukerma" : "the fish"}, so this needs your OK again. </strong>` : ""}${esc(c.text)}</div></div>${c.proof ? `<p class="check-proof">${esc(c.proof)} <a href="#row-${c.row_ids[0]}" data-proof="${c.row_ids[0]}">See the working</a></p>` : ""}<div class="check-actions"><button ${c.can_approve ? `data-approve="${c.id}"` : `data-fix="${c.row_ids[0] || ""}"`}>${esc(c.button)}</button>${c.alternative ? `<button class="text-button" data-alternative="${c.id}">${esc(c.alternative)}</button>` : ""}</div></div>`)).join("")}`;
}
function renderCovers() {
  $("#covers").innerHTML =
    `<h2>Covers this week</h2>${order.kitchen.bookings.map((b) => `<div class="cover-day"><span>${b.day}</span>${b.day === "Sat" && order.wedding ? `<span class="event">Wedding ${order.wedding.covers}</span>` : ""}<span class="count">${b.covers + (b.day === "Sat" ? order.wedding?.covers || 0 : 0)}</span></div>`).join("")}<p class="meta">Room bookings and events · demo kitchen</p>`;
}
function renderBudget() {
  let over = order.total > order.budget;
  $("#total").textContent = money(order.total);
  $("#edit-budget").textContent = `of ${money(order.budget)} budget`;
  $("#budget").classList.toggle("over", over);
  $("#budget-fill").style.width =
    Math.min(100, (order.total / order.budget) * 80) + "%";
  $("#budget-state").textContent = over
    ? `${money(order.total - order.budget)} over${order.checks.find((c) => c.id === "budget")?.approved ? " · OK’d this week" : ""}`
    : `${money(order.budget - order.total)} within budget`;
}
async function change(action, value, expectedRun = null) {
  if (expectedRun !== null && expectedRun !== storyRun)
    throw new Error("STOP_STORY");
  if (expectedRun === null && storyActive) stopStory();
  if (busy || !order) return;
  busy = true;
  try {
    const result = await api("/change", {
      token: order.token,
      action,
      value,
      photo_receipts: photoReceipts,
    });
    if (expectedRun !== null && expectedRun !== storyRun)
      throw new Error("STOP_STORY");
    render(result, false);
  } catch (e) {
    if (expectedRun !== null) throw e;
    notice(e.message);
  } finally {
    busy = false;
  }
}
function scrollToEl(el) {
  el?.scrollIntoView({
    behavior: reduced() ? "instant" : "smooth",
    block: "start",
  });
}
function openTell() {
  if (storyActive) stopStory();
  $("#tell-panel").hidden = false;
  $("#tell-content").hidden = false;
  $("#thinking").hidden = true;
  $("#listening").hidden = true;
  $("#tell-text").focus();
}
function thinking(text) {
  $("#tell-panel").hidden = false;
  $("#tell-content").hidden = true;
  $("#listening").hidden = true;
  $("#thinking").hidden = false;
  $("#transcript").textContent = text;
  ["read", "stock", "valio"].forEach((s) => {
    $("#step-" + s).classList.remove("done");
  });
}
function tick(step, label) {
  let el = $("#step-" + step);
  el.classList.add("done");
  el.innerHTML = icon("check") + esc(label);
}
async function tell(text, media) {
  if (storyActive) stopStory();
  if (busy || !order) return;
  busy = true;
  clearNotice();
  thinking(text || "Reading your recording…");
  try {
    const data = await api("/tell", {
      token: order.token,
      text,
      media,
      listened_tokens: listenedTokens,
      photo_receipts: photoReceipts,
    });
    listenedTokens = [];
    if (data.token && !data.rows) {
      order.token = data.token;
      order.evidence.calls = data.calls || order.evidence.calls;
    }
    if (data.reading?.status !== "readable") {
      notice(
        data.reading?.reason ||
          "Couldn't read that. Here's what I saw: " +
            (data.reading?.transcript || "No words."),
      );
      $("#transcript").textContent =
        data.reading?.transcript || "No words were clear enough to read.";
      $("#tell-content").hidden = false;
      return;
    }
    $("#transcript").textContent = data.reading.transcript;
    tick("read", "Read the wedding menu");
    tick("stock", "Checked your stock");
    tick(
      "valio",
      `Checked Valio availability for ${new Set(data.rows.map((r) => r.product_id)).size} products`,
    );
    render(data, true);
    setTimeout(() => {
      $("#tell-panel").hidden = true;
    }, 1500);
    setTimeout(() => {
      let first = order.rows.find((r) => r.change);
      if (first) scrollToEl($("#row-" + first.id));
    }, 400);
  } catch (e) {
    notice(e.message);
    $("#tell-content").hidden = false;
  } finally {
    busy = false;
  }
}
function showConfirmation() {
  let o = order;
  $("#layout").hidden = true;
  $("#result-summary").hidden = true;
  $("#photo-panel").hidden = true;
  $("#dock").hidden = true;
  $("#tell-panel").hidden = true;
  $("#intro").textContent = "Your kitchen sheet is signed off.";
  $("#confirmation").hidden = false;
  $("#confirmation").innerHTML =
    `<h1>${icon("check")}Order placed</h1><div class="order-number">${esc(o.confirmation.order_number)}</div>${o.deliveries.map((d) => `<div class="delivery-receipt"><div><strong>${dayName(d.date)} delivery</strong><p>${d.rows.filter((r) => r.units > 0).length} products · ${d.cutoff && new Date(d.cutoff) > new Date() ? "Cut-off met" : "Cut-off not supplied for some products"}</p></div><strong>${money(d.subtotal)}</strong></div>`).join("")}<div class="receipt-total"><span>This week<br><span class="meta">of ${money(o.budget)} budget${o.total > o.budget ? ", approved this week" : ""}</span></span><strong>${money(o.total)}</strong></div><button class="text-button" data-decisions>How this was decided</button><p class="demo-note">${esc(o.confirmation.notice)}</p><p class="mcp-note">Buying with your own ordering agent? It connects to Valio directly over <a href="/mcp/">MCP</a>.</p><button class="outline" id="start-again" style="margin-top:24px">Back to the kitchen</button>`;
  scrollToEl($("#confirmation"));
}
function showDecisions() {
  $("#decision-panel").hidden = false;
  let e = order.evidence;
  $("#decision-panel").innerHTML =
    `<div class="panel-title"><h2>How this was decided</h2><button class="icon-button" data-close="decision-panel" aria-label="Close decisions">×</button></div><p>${esc(e.fixture_note)}</p><h3>What the chef said</h3><p>${esc(order.wedding?.transcript || "Next week’s connected menu, stock and bookings.")}</p>${order.wedding?.read?.length ? `<h3>What we read</h3>${order.wedding.read.map((r) => `<p>${esc(r.word)}</p>`).join("")}` : ""}<h3>Your guardrails</h3><ul>${e.guardrails.map((r) => `<li>${esc(r)}</li>`).join("")}</ul><h3>Your OKs and changes</h3>${e.events.map((r) => `<p>${esc(r.at || "")} · ${esc(r.action)}${r.check ? " · " + esc(r.check) : ""}${r.text ? " · " + esc(r.text) : ""}${r.note ? " · " + esc(r.note) : ""}</p>`).join("") || "<p>Everything is within your kitchen rules.</p>"}<h3>Each choice, with its reason</h3>${e.decisions.map((d) => `<p><strong>${esc(order.rows.find((r) => r.product_id === d.product)?.name || d.product)}</strong><br>${esc(d.reason)}</p>`).join("")}<p class="meta">${esc(e.price_note)}</p><details><summary>Technical receipt · every supplier and understanding call</summary><p>Each Valio call carries your customer account and the requested delivery date. Cached responses are marked. No credentials are included.</p><details><summary>Open the supplier call record</summary><pre>${esc(JSON.stringify(e.calls, null, 2))}</pre><p>MCP for buyers with their own agents: <a href="/mcp/">${esc(location.origin)}/mcp/</a></p></details></details>`;
  scrollToEl($("#decision-panel"));
}
// No endpoint names or raw receipts appear until the chef opens the technical receipt.
document.addEventListener("click", async (ev) => {
  let t = ev.target.closest("button,a");
  if (!t) return;
  if (t.dataset.close) {
    $("#" + t.dataset.close).hidden = true;
    return;
  }
  if (t.dataset.working) {
    let id = t.dataset.working;
    expanded.has(id) ? expanded.delete(id) : expanded.add(id);
    $("#working-" + id).hidden = !expanded.has(id);
    t.setAttribute("aria-expanded", expanded.has(id));
    return;
  }
  if (t.dataset.step) {
    if (t.dataset.repeated === "yes") {
      t.dataset.repeated = "";
      return;
    }
    let r = order.rows.find((r) => r.id === t.dataset.id);
    await change("quantity", {
      id: r.id,
      units: r.units + Number(t.dataset.step),
    });
    return;
  }
  if (t.dataset.approve) {
    await change("approve", t.dataset.approve);
    return;
  }
  if (t.dataset.unapprove) {
    await change("unapprove", t.dataset.unapprove);
    return;
  }
  if (t.dataset.restore) {
    await change("restore", t.dataset.restore);
    return;
  }
  if (t.dataset.fix !== undefined) {
    let c = order.checks.find(
      (c) => c.row_ids[0] === t.dataset.fix && !c.can_approve,
    );
    if (c?.id.startsWith("short-") || c?.id.startsWith("stock-"))
      await change("restore", t.dataset.fix);
    else openTell();
    return;
  }
  if (t.dataset.proof) {
    ev.preventDefault();
    expanded.add(t.dataset.proof);
    $("#working-" + t.dataset.proof).hidden = false;
    scrollToEl($("#row-" + t.dataset.proof));
    return;
  }
  if (t.hasAttribute("data-decisions")) {
    ev.preventDefault();
    showDecisions();
    return;
  }
  if (t.dataset.alternative) {
    if (t.dataset.alternative === "pack") await change("small-cream");
    else if (t.dataset.alternative === "budget") {
      let r = [...order.rows].sort((a, b) => b.total - a.total)[0];
      expanded.add(r.id);
      $("#working-" + r.id).hidden = false;
      scrollToEl($("#row-" + r.id));
      notice(
        `${r.name} is the costliest product, ${money(r.total)}. Reduce the menu in Tell Valio, or approve this week’s budget.`,
      );
    } else openTell();
    return;
  }
  if (t.id === "only-changes") {
    onlyChanges = !onlyChanges;
    render(order);
    t.textContent = onlyChanges ? "Show full order" : "Show only what changed";
    return;
  }
  if (t.id === "undo-wedding" || t.hasAttribute("data-undo-menu")) {
    onlyChanges = false;
    $("#result-summary").hidden = true;
    await change("undo-wedding");
    return;
  }
  if (t.id === "start-again") {
    location.reload();
    return;
  }
  if (t.dataset.add) {
    await change("add", t.dataset.add);
    if (!$("#notice").hidden) return;
    $("#search-panel").hidden = true;
    return;
  }
});
let repeatTimer = null,
  repeatInterval = null;
document.addEventListener("pointerdown", (ev) => {
  let b = ev.target.closest("[data-step]");
  if (!b || b.disabled) return;
  repeatTimer = setTimeout(() => {
    b.dataset.repeated = "yes";
    repeatInterval = setInterval(() => {
      let r = order.rows.find((r) => r.id === b.dataset.id);
      if (r && r.units + Number(b.dataset.step) >= 0)
        change("quantity", {
          id: r.id,
          units: r.units + Number(b.dataset.step),
        });
    }, 400);
  }, 450);
});
for (const type of ["pointerup", "pointercancel"])
  document.addEventListener(type, () => {
    clearTimeout(repeatTimer);
    clearInterval(repeatInterval);
  });
$("#keyboard").onclick = openTell;
$("#close-tell").onclick = () => ($("#tell-panel").hidden = true);
$("#example").onclick = () => {
  $("#tell-text").value = "Wedding Saturday, 120 guests, salmon and lemon tart";
  $("#tell-text").focus();
};
$("#tell-form").onsubmit = (ev) => {
  ev.preventDefault();
  if (!$("#tell-text").value.trim()) {
    notice("Tell Valio what changed, or use the wedding menu.");
    return;
  }
  tell($("#tell-text").value.trim());
};
$("#place").onclick = () => {
  if (!order) return;
  if (!order.can_place) {
    scrollToEl($("#checks"));
    return;
  }
  change("place");
};
$("#edit-budget").onclick = () => {
  $("#budget-editor").hidden = false;
  $("#budget-input").value = order.budget;
  $("#budget-input").focus();
};
$("#budget-form").onsubmit = async (ev) => {
  ev.preventDefault();
  await change("budget", Number($("#budget-input").value));
  $("#budget-editor").hidden = true;
};
$("#add-product").onclick = () => {
  $("#search-panel").hidden = false;
  $("#search-input").focus();
};
$("#search-form").onsubmit = async (ev) => {
  ev.preventDefault();
  let el = $("#search-results");
  el.innerHTML = "<p>Looking in the Valio catalogue…</p>";
  try {
    let r = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: $("#search-input").value, limit: 8 }),
    });
    if (!r.ok) throw new Error();
    let data = await r.json();
    el.innerHTML = data.results.length
      ? data.results
          .filter(
            (p) =>
              !p.contains.includes("nuts") &&
              !p.contains.includes("peanuts") &&
              !p.may_contain.includes("nuts") &&
              !p.may_contain.includes("peanuts"),
          )
          .map(
            (p) =>
              `<div class="search-product"><strong>${esc(p.name_fi || p.name)}</strong><p class="meta">${p.pack ? n(p.pack) + " " + esc(p.pack_dim) : "Pack checked before adding"} · ${esc(p.contains.join(", ") || "No declared allergens")}</p><button data-add="${esc(p.id)}">Add to Friday</button></div>`,
          )
          .join("")
      : "<p>No products found. Try a Finnish product name.</p>";
  } catch {
    el.innerHTML = "<p>Could not reach the catalogue. Try again.</p>";
  }
};
function bytes64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 8192)
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(binary);
}
async function startRecording() {
  if (storyActive) stopStory();
  if (busy || recordingPending || recorder?.state === "recording") return;
  releaseRequested = false;
  recordingPending = true;
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
      throw new Error(
        "Recording is unavailable in this browser. Type your change in Tell Valio.",
      );
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (releaseRequested) {
      audioStream.getTracks().forEach((t) => t.stop());
      return;
    }
    let chunks = [],
      partialBusy = false,
      partialCount = 0;
    listenedTokens = [];
    let mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((t) =>
      MediaRecorder.isTypeSupported(t),
    );
    recorder = new MediaRecorder(
      audioStream,
      mime ? { mimeType: mime } : undefined,
    );
    recorder.ondataavailable = async (e) => {
      if (e.data.size) chunks.push(e.data);
      if (
        recorder.state !== "recording" ||
        partialBusy ||
        partialCount >= 4 ||
        chunks.length % 3 !== 0
      )
        return;
      partialBusy = true;
      partialCount++;
      try {
        const part = new Blob(chunks, { type: recorder.mimeType });
        const result = await api("/listen", {
          token: order.token,
          media: {
            mime: part.type.split(";")[0],
            data: bytes64(await part.arrayBuffer()),
          },
        });
        if (recorder.state === "recording") {
          if (result.transcript)
            $("#live-transcript").textContent = result.transcript;
          listenedTokens.push(result.call_token);
        }
      } catch {
        /* A partial recording can end mid-word. Final audio is checked on release. */
      } finally {
        partialBusy = false;
      }
    };
    recorder.onstop = async () => {
      audioStream.getTracks().forEach((t) => t.stop());
      if (audioContext) {
        audioContext.close();
        audioContext = null;
      }
      let blob = new Blob(chunks, { type: recorder.mimeType });
      if (blob.size < 500) {
        notice("Didn't catch that. Hold and say it again, or type it.");
        openTell();
        return;
      }
      if (blob.size > 6000000) {
        notice("Recording is too long. Say the change in one short sentence.");
        return;
      }
      tell(null, {
        mime: blob.type.split(";")[0],
        data: bytes64(await blob.arrayBuffer()),
      });
    };
    recorder.start(1000);
    $("#live-transcript").textContent = "Listening… release to send";
    $("#tell-panel").hidden = false;
    $("#tell-content").hidden = true;
    $("#thinking").hidden = true;
    $("#listening").hidden = false;
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    let analyser = audioContext.createAnalyser();
    audioContext.createMediaStreamSource(audioStream).connect(analyser);
    let buf = new Uint8Array(analyser.fftSize);
    function level() {
      if (!audioContext || recorder.state !== "recording") return;
      analyser.getByteTimeDomainData(buf);
      let rms =
        Math.sqrt(buf.reduce((a, x) => a + (x - 128) ** 2, 0) / buf.length) /
        128;
      $("#level").style.transform = `scaleX(${Math.min(1, 0.05 + rms * 5)})`;
      requestAnimationFrame(level);
    }
    level();
  } catch (e) {
    notice(
      e.message ||
        "Microphone permission was not granted. Type your change in Tell Valio.",
    );
    openTell();
  } finally {
    recordingPending = false;
  }
}
function stopRecording() {
  releaseRequested = true;
  if (recorder?.state === "recording") recorder.stop();
}
$("#mic").addEventListener("pointerdown", (ev) => {
  if (ev.button !== 0) return;
  ev.preventDefault();
  $("#mic").setPointerCapture(ev.pointerId);
  startRecording();
});
$("#mic").addEventListener("pointerup", stopRecording);
$("#mic").addEventListener("pointercancel", stopRecording);
$("#mic").addEventListener("keydown", (ev) => {
  if ([" ", "Enter"].includes(ev.key) && !ev.repeat) {
    ev.preventDefault();
    startRecording();
  }
});
$("#mic").addEventListener("keyup", (ev) => {
  if ([" ", "Enter"].includes(ev.key)) {
    ev.preventDefault();
    stopRecording();
  }
});
$("#camera").onclick = () => {
  if (!order) return;
  $("#photo-file").click();
};
$("#photo-file").onchange = async () => {
  if (storyActive) stopStory();
  const readRun = ++photoReadRun;
  let file = $("#photo-file").files[0];
  if (!file) return;
  if (file.size > 6000000) {
    notice("Choose a photo smaller than 6 MB.");
    return;
  }
  let data = bytes64(await file.arrayBuffer());
  if (readRun !== photoReadRun) return;
  photoSrc = "data:" + file.type + ";base64," + data;
  $("#photo-panel").hidden = false;
  $("#photo-panel").innerHTML =
    "<h2>Reading the final menu…</h2><p>Your photo goes to Gemini. Your order stays unchanged until you check it.</p>";
  scrollToEl($("#photo-panel"));
  try {
    const requestToken = order.token;
    let result = await api("/photo", {
      token: requestToken,
      media: { mime: file.type, data },
    });
    if (result.read_token) photoReceipts.push(result.read_token);
    // A photo can finish after the chef changed the sheet. Never restore its older signed state.
    if (result.token && order.token === requestToken) {
      order.token = result.token;
      order.evidence.calls = result.calls || order.evidence.calls;
    } else if (result.call) order.evidence.calls.push(result.call);
    if (readRun !== photoReadRun) return;
    photo = result.reading;
    readToken = result.read_token;
    renderPhoto();
  } catch (e) {
    if (readRun !== photoReadRun) return;
    $("#photo-panel").innerHTML =
      `<h2>Couldn't read it</h2><p>${esc(e.message)}</p><button id="retry-photo" class="outline">Choose another photo</button>`;
    $("#retry-photo").onclick = () => $("#photo-file").click();
  } finally {
    $("#photo-file").value = "";
  }
};
const dishNames = {
  salmon: "Salmon with dill potatoes",
  soup: "Lohikeitto",
  whitefish: "Paistettu siika",
  tart: "Lemon tart",
  cheeseboard: "Juustolautanen",
};
function renderPhoto() {
  let good = photo.status === "readable",
    correctable =
      photo.status === "uncertain" &&
      photo.dishes.length > 0 &&
      Number.isInteger(photo.covers),
    prior = order.wedding?.dishes || [];
  let added = photo.dishes.filter(
    (d) => !prior.some((p) => p.recipe === d.recipe),
  );
  let removed = prior.filter(
    (d) => !photo.dishes.some((p) => p.recipe === d.recipe),
  );
  $("#photo-panel").hidden = false;
  $("#photo-panel").innerHTML =
    `<div class="photo-heading"><h2>${good ? "Check the final menu" : "Couldn't read it"}</h2><button class="icon-button" data-close="photo-panel" aria-label="Close photo">×</button></div><div class="photo-grid"><div class="photo-image"><img src="${photoSrc}" alt="Chef's final wedding menu on a whiteboard"><div id="photo-outline" class="photo-outline" hidden></div></div><div class="photo-reading"><h3>What we read</h3>${
      good || correctable
        ? `${removed.map((d) => `<p>Removed: ${esc(dishNames[d.recipe])}</p>`).join("")}${photo.dishes
            .map((d, i) => {
              let old = prior.find((p) => p.recipe === d.recipe);
              let word = !old
                ? "Added"
                : old.covers < d.covers
                  ? "More"
                  : old.covers > d.covers
                    ? "Less"
                    : "Menu";
              return `<label class="dish-edit"><span>${word}:</span><select data-dish="${i}" aria-label="Dish ${i + 1}">${Object.entries(
                dishNames,
              )
                .map(
                  ([k, v]) =>
                    `<option value="${k}" ${d.recipe === k ? "selected" : ""}>${esc(v)}</option>`,
                )
                .join(
                  "",
                )}</select><input type="number" data-covers="${i}" min="1" max="1000" value="${d.covers}" aria-label="Portions of ${esc(dishNames[d.recipe])}"></label>`;
            })
            .join("")}`
        : `<p>${esc(photo.reason)}</p>`
    }${photo.read.map((r, i) => `<button class="read-word${r.uncertain ? " uncertain" : ""}" data-word="${i}"><span>${esc(r.word)}</span>${r.uncertain ? '<span class="meta">Check this word</span>' : ""}</button>`).join("")}<p class="meta">${good ? "Check the dish and portion count in place. Tap handwriting to see it on the photo." : "Here’s what I saw: " + esc(photo.transcript || "No legible words. No changes have been made to your order.")}</p></div></div>${correctable ? `<label class="confirm-words"><input type="checkbox" id="confirm-words"> I checked the dishes and portions against this photo.</label>` : ""}<div class="photo-actions"><button class="outline" id="retry-photo">Choose another photo</button><button class="solid" id="apply-photo" ${good ? "" : "disabled"}>Update order</button></div>`;
  $("#retry-photo").onclick = () => $("#photo-file").click();
  if ($("#confirm-words"))
    $("#confirm-words").onchange = () => {
      const checked = $("#confirm-words").checked;
      $("#apply-photo").disabled = !checked;
      if (checked) {
        photo.status = "readable";
        photo.uncertain = [];
        photo.read.forEach((r) => (r.uncertain = false));
      }
    };
  $$("[data-word]").forEach(
    (b) => (b.onclick = () => highlightWord(Number(b.dataset.word))),
  );
  $$("[data-dish]").forEach(
    (el) =>
      (el.onchange = () => {
        photo.dishes[Number(el.dataset.dish)].recipe = el.value;
      }),
  );
  $$("[data-covers]").forEach(
    (el) =>
      (el.oninput = () => {
        photo.dishes[Number(el.dataset.covers)].covers = Number(el.value);
      }),
  );
  $("#apply-photo").onclick = () => applyPhoto();
}
function highlightWord(index) {
  let box = photo.read[index].box,
    img = $(".photo-image img"),
    frame = img.parentElement,
    outline = $("#photo-outline");
  let rect = img.getBoundingClientRect(),
    ratio = Math.min(
      rect.width / img.naturalWidth,
      rect.height / img.naturalHeight,
    ),
    w = img.naturalWidth * ratio,
    h = img.naturalHeight * ratio;
  outline.hidden = false;
  outline.style.left = (rect.width - w) / 2 + (box[1] / 1000) * w + "px";
  outline.style.top = (rect.height - h) / 2 + (box[0] / 1000) * h + "px";
  outline.style.width = ((box[3] - box[1]) / 1000) * w + "px";
  outline.style.height = ((box[2] - box[0]) / 1000) * h + "px";
}
async function applyPhoto(expectedRun = null) {
  if (expectedRun !== null && expectedRun !== storyRun)
    throw new Error("STOP_STORY");
  if (expectedRun === null && storyActive) stopStory();
  if (busy) return;
  busy = true;
  try {
    let updated = await api("/photo/apply", {
      token: order.token,
      read_token: readToken,
      reading: photo,
      photo_receipts: photoReceipts,
      confirmed: !!$("#confirm-words")?.checked,
    });
    if (expectedRun !== null && expectedRun !== storyRun)
      throw new Error("STOP_STORY");
    $("#photo-panel").hidden = true;
    render(updated, true);
    scrollToEl($("#main"));
  } catch (e) {
    if (expectedRun !== null) throw e;
    notice(e.message);
  } finally {
    busy = false;
  }
}
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function playStory() {
  if (busy || !order || storyActive) return;
  storyActive = true;
  const run = ++storyRun;
  const current = () => {
    if (run !== storyRun) throw new Error("STOP_STORY");
  };
  $("#story-strip").hidden = false;
  $("#play").disabled = true;
  const beat = async (text, ms) => {
    current();
    $("#story-caption").textContent = text;
    await delay(ms);
    if (run !== storyRun) throw new Error("STOP_STORY");
  };
  try {
    await beat(
      "Friday. The weekly order is ready, with every quantity worked out.",
      5000,
    );
    const reading = await api("/story-reading");
    current();
    if (!reading.ready)
      throw new Error(
        "The recorded story is not ready. Use Tell Valio to run the wedding live.",
      );
    thinking("Wedding Saturday, 120 guests, salmon and lemon tart");
    await beat("The wedding call. Tell Valio what changed.", 5000);
    tick("read", "Read the wedding menu");
    await delay(600);
    current();
    tick("stock", "Checked your stock");
    let updated = await api("/story-wedding", {
      token: order.token,
      wedding_token: reading.wedding_token,
    });
    current();
    tick("valio", "Checked Valio prices and availability");
    render(updated, true);
    await beat(
      "Added the wedding. The sheet shows the stock, pack rounding and budget.",
      8500,
    );
    $("#tell-panel").hidden = true;
    scrollToEl($("#checks"));
    for (const id of ["swap", "pack", "budget"]) {
      if (order.checks.some((c) => c.id === id && !c.approved)) {
        await beat(
          id === "swap"
            ? "Check the fish: same cooking method and no new allergens."
            : id === "pack"
              ? "Check the cream: larger pack, lower price per litre, booked recipes."
              : "Check the budget. This OK applies to this week only.",
          6500,
        );
        await change("approve", id, run);
        current();
      }
    }
    let cream = order.rows.find(
      (r) =>
        r.role === "cream" &&
        order.checks.find((c) => c.id === "pack")?.row_ids.includes(r.id),
    );
    if (cream) {
      await beat(
        "One extra cream pack changes the approval. The order locks again.",
        5000,
      );
      await change("quantity", { id: cream.id, units: cream.units + 1 }, run);
      current();
      scrollToEl($("#checks"));
      await delay(4000);
      current();
      for (const c of [...order.checks]) {
        if (!c.approved && c.can_approve) await change("approve", c.id, run);
      }
    }
    await beat("The chef photographs the final wedding menu.", 4500);
    photo = structuredClone(reading.photo);
    readToken = reading.read_token;
    photoSrc = "/whiteboards/menu-1.jpg";
    renderPhoto();
    scrollToEl($("#photo-panel"));
    await beat(
      "What we read: whitefish, lemon tart and a cheese board. Check before updating.",
      8000,
    );
    await applyPhoto(run);
    current();
    await beat(
      "The final menu updates the order. Check the new total before placing.",
      6000,
    );
    for (const c of [...order.checks])
      if (!c.approved && c.can_approve) await change("approve", c.id, run);
    if (order.can_place) {
      await beat("All checked. Place the order.", 5000);
      await change("place", undefined, run);
      current();
      await beat(
        "Order placed. The signed sheet keeps every reason and every OK.",
        5000,
      );
    } else
      throw new Error(
        "Supply changed. Check the order before continuing the story.",
      );
  } catch (e) {
    if (e.message !== "STOP_STORY") notice(e.message);
  } finally {
    if (run === storyRun) {
      storyActive = false;
      $("#play").disabled = false;
    }
  }
}
$("#play").onclick = playStory;
function stopStory() {
  storyRun++;
  storyActive = false;
  $("#story-caption").textContent =
    "Story stopped. You can keep checking the order.";
  $("#play").disabled = false;
  $("#tell-panel").hidden = true;
}
$("#stop-story").onclick = stopStory;
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    for (const s of ["#tell-panel", "#search-panel", "#budget-editor"])
      $(s).hidden = true;
    stopRecording();
  }
});
setInterval(() => {
  if (order)
    $$(".cutoff").forEach((el) => {
      const d = order.deliveries.find((d) => d.date === el.dataset.date);
      if (d) el.innerHTML = cutoff(d);
    });
}, 60000);
(async () => {
  try {
    render(await api(""));
  } catch (e) {
    $("#sheet").innerHTML =
      `<div style="padding:24px"><h2>Your order is waiting for Valio</h2><p style="margin:12px 0">${esc(e.message)}</p><button class="outline" onclick="location.reload()">Try again</button></div>`;
    $("#checks").innerHTML =
      '<div class="all-clear">The order stays on hold until prices are confirmed.</div>';
    $("#place").textContent = "Waiting for Valio";
  }
})();
