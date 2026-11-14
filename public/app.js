const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const eur = n => "€" + Number(n || 0).toLocaleString("en-IE", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const eur0 = n => "€" + Number(n || 0).toLocaleString("en-IE", {maximumFractionDigits: 0});
const num = (n, d = 1) => Number(n || 0).toLocaleString("en-IE", {minimumFractionDigits: 0, maximumFractionDigits: d});
const qty = (v, unit) => unit === "kg" && v > 0 && v < 1 ? `${num(v * 1000, 0)} g` : `${num(v, 1)} ${unit}`;
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const DIETS = ["vegan", "vegetarian", "gluten-free", "milk-free"];
const fmtDate = d => { const x = new Date(d + "T12:00:00"); return isNaN(x) ? String(d ?? "") : x.toLocaleDateString("en-GB", {weekday: "short", day: "numeric", month: "short"}); };
const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const APPROVER = "Head chef (one-tap approval)";
const QUICK_EXAMPLES = ["1,000 litres of lactose-free milk by Monday", "40 kg salmon fillet by Wednesday", "200 kg peeled potatoes for Tuesday"];

let state = {kitchens: {}, samples: [], services: [], planned: [], order: null, placed: {}, holds: {}, auditFilter: "all", busy: false};

function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 4200); }

async function api(path, body) {
  const r = await fetch(path, body ? {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)} : {});
  const j = await r.json().catch(() => ({error: "Server error " + r.status}));
  if (!r.ok || j.error) throw new Error(j.error || j.detail || ("HTTP " + r.status));
  return j;
}

/* ---------------- tabs ---------------- */
function showView(name) {
  $$(".tab").forEach(x => { const on = x.dataset.view === name; x.classList.toggle("active", on); x.setAttribute("aria-selected", on); });
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + name));
  if (name === "eval") renderEval();
  window.scrollTo(0, 0);
}
$$(".tab").forEach(b => b.onclick = () => showView(b.dataset.view));

/* ---------------- the 4-step flow bar ---------------- */
const FLOW_IDLE = ["A menu, or one line", "Only the shortlist is priced, at your prices", "One cart per delivery day, price fixed", "Agent within policy, or you sign off"];
function setFlow(i, st, text) {
  const li = $$("#flow li")[i]; if (!li) return;
  li.dataset.state = st;
  if (text != null) $(".s", li).textContent = text;
  if (st === "now") li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
}
function resetFlow() { FLOW_IDLE.forEach((t, i) => setFlow(i, "idle", t)); }
function setStage(s) { $("#main").dataset.stage = s; }

function requestSummary() {
  const items = state.planned, direct = items.filter(i => i.direct), dishes = items.filter(i => !i.direct);
  const parts = [];
  if (dishes.length) parts.push(`${plural(dishes.length, "menu line", "menu lines")}, ${num(dishes.reduce((a, i) => a + (+i.covers || 0), 0), 0)} covers`);
  if (direct.length === 1) { const d = direct[0]; parts.push(`${d.qty ? num(d.qty, 1) + " " + (d.unit || "") + " " : ""}${d.ingredient || d.text}, by ${fmtDate(d.date)}`); }
  else if (direct.length) parts.push(plural(direct.length, "direct request", "direct requests"));
  return parts.join(" + ") || "Request received";
}
function flowFromOrder() {
  const o = state.order; if (!o) return;
  const ds = o.deliveries || [], lines = ds.flatMap(d => d.lines || []);
  const u = o.api_usage;
  setFlow(0, "done", requestSummary());
  setFlow(1, "done", u ? `${num(u.price_lookups, 0)} of ${num(u.catalogue_size, 0)} products priced, ${apiCalls(u)}` : `${lines.length} products matched`);
  const nPlaced = ds.filter((d, i) => state.placed[i]).length;
  const need = ds.filter((d, i) => needsApproval(i) && !state.placed[i]).length;
  const auto = ds.filter((d, i) => !needsApproval(i) && !state.placed[i]).length;
  if (!ds.length) { setFlow(2, "warn", "Nothing could be sourced in time"); setFlow(3, "idle", "Nothing to approve"); return; }
  if (nPlaced === ds.length) {
    setFlow(2, "done", `${plural(nPlaced, "order", "orders")} placed, ${eur(o.total)} at fixed prices`);
    const byHuman = Object.values(state.placed).filter(p => p.human).length;
    setFlow(3, "done", byHuman ? `Signed off by head chef${byHuman < nPlaced ? `, ${nPlaced - byHuman} auto-approved` : ""}` : "Auto-approved within policy");
  } else {
    setFlow(2, "done", `${plural(lines.length, "line", "lines")} in ${plural(ds.length, "delivery", "deliveries")}, ${eur(o.total)} fixed${nPlaced ? `, ${nPlaced} placed` : ""}`);
    if (need) setFlow(3, "warn", `${plural(need, "delivery needs", "deliveries need")} your sign-off${auto ? `, ${auto} auto-approved` : ""}`);
    else setFlow(3, "ok", `Auto-approved: ${plural(auto, "delivery", "deliveries")} within policy`);
  }
}

/* ---------------- kitchen & samples ---------------- */
function customer() { return $("#kitchen").value; }
function renderPolicy() {
  const k = state.kitchens[customer()]; if (!k) return;
  const p = k.policy || {}, ff = p.free_from || [];
  const rules = [
    p.lactose_free_dairy ? "Lactose-free dairy only" : "",
    ff.length ? "Free from " + ff.join(", ") + (p.strict_may_contain ? " (incl. “may contain”)" : "") : "",
    `Agent may approve up to <b>${eur0(p.auto_approve_limit_eur)}</b> per delivery`,
    p.allow_substitutes === "same_ingredient_auto" ? "Same-ingredient swaps allowed" : "Every swap needs sign-off",
  ].filter(Boolean);
  $("#policy").innerHTML = `<div class="policy-k">Guardrails for <b>${esc((k.name || "").split(" (")[0])}</b></div>
    <ul>${rules.map(r => `<li>${r}</li>`).join("")}</ul>`;
}
function sampleStats(s) {
  const items = (s.services || []).flatMap(x => x.items || []);
  return `${plural(items.length, "dish", "dishes")} · ${num(items.reduce((a, i) => a + (+i.covers || 0), 0), 0)} covers`;
}
function loadSample(s) {
  if (!s) return;
  $$(".sample").forEach(b => { const on = b.dataset.id === s.id; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on); });
  if (state.kitchens[s.customer]) $("#kitchen").value = s.customer;
  renderPolicy();
  state.services = JSON.parse(JSON.stringify(s.services || []));
  renderServices();
}

/* ---------------- menu editor ---------------- */
function editorSummary() {
  const items = state.services.flatMap(s => s.items || []).filter(i => (i.text || "").trim());
  const covers = items.reduce((a, i) => a + (i.direct ? 0 : (+i.covers || 0)), 0);
  $("#editor-sum").innerHTML = items.length
    ? `Review or edit the menu <span class="muted">· ${plural(items.length, "line", "lines")}${covers ? `, ${num(covers, 0)} covers` : ""}</span>`
    : "Write your menu lines";
}
function renderServices() {
  const box = $("#services"); box.innerHTML = "";
  state.services.forEach((s, si) => {
    s.items = s.items || [];
    const el = document.createElement("div"); el.className = "service";
    el.innerHTML = `<div class="service-head">
        <input type="date" value="${esc(s.date)}" aria-label="Service date">
        <input class="meal" value="${esc(s.meal || "")}" placeholder="Meal (e.g. Lunch buffet)" aria-label="Meal">
        <button class="x" type="button" title="Remove service" aria-label="Remove service">×</button></div>
      <div class="items"></div><button class="add-item" type="button">+ menu line</button>`;
    $("input[type=date]", el).onchange = e => s.date = e.target.value;
    $("input.meal", el).oninput = e => s.meal = e.target.value;
    $(".service-head .x", el).onclick = () => { state.services.splice(si, 1); renderServices(); };
    const items = $(".items", el);
    s.items.forEach((it, ii) => {
      const r = document.createElement("div"); r.className = "item" + (it.direct ? " direct" : "");
      r.innerHTML = `<input value="${esc(it.text)}" placeholder="Dish as you'd write it" aria-label="Menu line">
        ${it.direct ? `<span class="direct-qty" title="Direct product request">${esc(num(it.qty, 1))} ${esc(it.unit || "")}</span>`
                    : `<input class="covers" type="number" min="1" value="${esc(it.covers)}" aria-label="Covers">`}
        <button class="x" type="button" aria-label="Remove line">×</button>
        ${it.direct ? `<div class="diet"><span class="dnote">Direct request: ${esc(it.ingredient || "")}</span></div>`
                    : `<div class="diet">${DIETS.map(d => `<button type="button" class="dchip ${it.diet?.includes(d) ? "on" : ""}" data-d="${d}" aria-pressed="${!!it.diet?.includes(d)}">${d}</button>`).join("")}</div>`}`;
      $("input", r).oninput = e => { it.text = e.target.value; editorSummary(); };
      const cv = $(".covers", r); if (cv) cv.oninput = e => { it.covers = +e.target.value; editorSummary(); };
      $(".x", r).onclick = () => { s.items.splice(ii, 1); renderServices(); };
      $$(".dchip", r).forEach(c => c.onclick = () => {
        it.diet = it.diet || []; const d = c.dataset.d;
        it.diet = it.diet.includes(d) ? it.diet.filter(x => x !== d) : [...it.diet, d];
        c.classList.toggle("on"); c.setAttribute("aria-pressed", c.classList.contains("on"));
      });
      items.appendChild(r);
    });
    $(".add-item", el).onclick = () => { s.items.push({text: "", covers: 100, diet: []}); renderServices(); };
    box.appendChild(el);
  });
  editorSummary();
}
$("#add-service").onclick = () => { state.services.push({date: "2026-11-20", meal: "Lunch", items: [{text: "", covers: 100, diet: []}]}); renderServices(); };
$("#paste-btn").onclick = () => { $("#paste-box").classList.toggle("hidden"); if (!$("#paste-box").classList.contains("hidden")) $("#paste-text").focus(); };
$("#parse-btn").onclick = async () => {
  const b = $("#parse-btn"); b.disabled = true; b.textContent = "Reading…";
  try {
    const r = await api("/api/parse-menu", {text: $("#paste-text").value});
    state.services = r.services || []; renderServices(); $("#paste-box").classList.add("hidden");
    $$(".sample").forEach(x => { x.classList.remove("on"); x.setAttribute("aria-pressed", "false"); });
  } catch (e) { toast("Could not read the menu: " + e.message); }
  b.disabled = false; b.textContent = "Read menu";
};
$("#kitchen").onchange = renderPolicy;

/* ---------------- planning ---------------- */
let stepTimer, clockTimer;
function showWorking(on, title) {
  $("#working").classList.toggle("hidden", !on);
  clearInterval(stepTimer); clearInterval(clockTimer);
  if (!on) return;
  $("#result").classList.add("hidden");
  $("#work-title").textContent = title || "Building your order";
  const t0 = Date.now(); $("#elapsed").textContent = "0 s";
  clockTimer = setInterval(() => $("#elapsed").textContent = Math.round((Date.now() - t0) / 1000) + " s", 1000);
  $$("#work-steps li").forEach(l => l.className = "");
}
function startWorkSteps() {
  // Indicative progress: the backend answers once, so the sub-steps advance on a timer and the last one waits for the reply.
  const li = $$("#work-steps li"); let i = 0;
  const mark = () => {
    li.forEach((l, k) => l.className = k < i ? "done" : k === i ? "now" : "");
    const f = +li[i].dataset.flow;
    for (let k = 1; k < 4; k++) setFlow(k, k < f ? "done" : k === f ? "now" : "idle", k === f ? li[i].textContent : FLOW_IDLE[k]);
  };
  mark();
  clearInterval(stepTimer);
  stepTimer = setInterval(() => { if (i < li.length - 1) { i++; mark(); } }, 4200);
}
function setBusy(on) {
  state.busy = on;
  ["#plan-btn", "#quick-btn"].forEach(s => $(s).disabled = on);
}
function toResultTop() { window.scrollTo({top: 0, behavior: calm() ? "auto" : "smooth"}); }  // hero is hidden once a run starts, so the flow bar is at the top

async function run(getServices, title) {
  if (state.busy) return;
  const hadOrder = !!state.order;
  setBusy(true); setStage("working"); resetFlow(); showWorking(true, title); toResultTop();
  try {
    setFlow(0, "now", "Reading your request");
    const services = await getServices();
    if (!services.length) throw new Error("Nothing to order yet. Add at least one line.");
    state.planned = services.flatMap(s => s.items.map(it => ({...it, date: s.date, meal: s.meal})));
    setFlow(0, "done", requestSummary());
    startWorkSteps();
    const order = await api("/api/plan", {services, customer: customer()});
    state.order = order; state.placed = {}; state.holds = {}; state.auditFilter = "all";
    showWorking(false); setStage("result"); renderOrder();
  } catch (e) {
    showWorking(false);
    toast("Planning failed: " + e.message);
    if (hadOrder) { setStage("result"); $("#result").classList.remove("hidden"); flowFromOrder(); } else { setStage("landing"); resetFlow(); }
  }
  setBusy(false);
}
$("#plan-btn").onclick = () => {
  const services = state.services.map(s => ({...s, items: (s.items || []).filter(i => (i.text || "").trim())})).filter(s => s.items.length);
  if (!services.length) { $("#editor").open = true; return toast("Add at least one menu line."); }
  run(async () => services, "Building your order");
};
$("#quick-btn").onclick = () => {
  const text = $("#quick-text").value.trim();
  if (!text) { $("#quick-text").focus(); return toast("Type what you need, for example: 40 kg salmon fillet by Wednesday."); }
  run(async () => {
    const r = await api("/api/parse-menu", {text});
    const services = (r.services || []).map(s => ({...s, items: (s.items || []).filter(i => (i.text || "").trim())})).filter(s => s.items.length);
    state.services = JSON.parse(JSON.stringify(services)); renderServices();
    $$(".sample").forEach(x => { x.classList.remove("on"); x.setAttribute("aria-pressed", "false"); });
    return services;
  }, "Sourcing your request");
};
$("#quick-text").addEventListener("keydown", e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#quick-btn").click(); });

/* ---------------- result ---------------- */
const isDirectItem = idx => !!state.planned[idx]?.direct;
const isDirectLine = l => (l.allocations || []).length > 0 && l.allocations.every(a => isDirectItem(a.item));
const cu = l => (l.comparison_unit || "").toUpperCase() === "L" ? "L" : "kg";
function needsApproval(di) { const d = state.order.deliveries[di]; return d.status !== "auto_approved" || !!state.holds[di]; }

function dishStatus(o) {
  // per menu line: which ingredients got a product, which are gaps
  const lines = (o.deliveries || []).flatMap(d => d.lines || []);
  return (o.menu || []).map(m => {
    const got = [], subs = [];
    lines.forEach(l => (l.allocations || []).forEach(a => { if (a.item === m.idx) { got.push({l, a}); if (l.substitution) subs.push(l); } }));
    const gaps = (o.gaps || []).filter(g => (g.alloc || []).some(a => a.item === m.idx));
    return {...m, got, gaps, subs, direct: isDirectItem(m.idx)};
  });
}
function apiCalls(u, bold) {
  const n = +u.http_calls || 0;
  return n ? `${bold ? `<b>${num(n, 0)}</b>` : num(n, 0)} ${n === 1 ? "API call" : "API calls"}` : "no new API calls (cached)";
}
function apiChip(u) {
  if (!u) return "";
  return `<div class="api-chip" title="${esc(u.note || "")}">
    <span class="dot" aria-hidden="true"></span>
    <span>Priced <b>${num(u.price_lookups, 0)}</b> of ${num(u.catalogue_size, 0)} products · ${apiCalls(u, true)}</span>
  </div>`;
}

function renderOrder() {
  const o = state.order; $("#result").classList.remove("hidden");
  const ds0 = o.deliveries || [], lines = ds0.flatMap(d => d.lines || []);
  const ds = dishStatus(o);
  const allDirect = ds.length > 0 && ds.every(d => d.direct);
  const cookable = ds.filter(d => !d.gaps.filter(g => !g.optional).length && (d.got.length || !d.direct)).length;
  const holdDel = ds0.filter((d, i) => needsApproval(i)).length;
  const co2 = ds0.reduce((a, d) => a + (d.co2_kg || 0), 0);
  const u = o.api_usage;
  $("#summary").innerHTML = `<div class="sum-head">
      <div><p class="eyebrow">Draft order${o.draft_id ? " " + esc(o.draft_id) : ""}</p><h2>${esc((o.kitchen || "").split(" (")[0] || "Your kitchen")}</h2></div>
      ${apiChip(u)}</div>
    <div class="kpis">${[
      [`${cookable}/${ds.length}`, allDirect ? (ds.length === 1 ? "request fully sourced" : "requests fully sourced") : "dishes fully sourced", cookable === ds.length ? "good" : "bad"],
      [lines.length, `${lines.length === 1 ? "product" : "products"} in ${plural(ds0.length, "delivery", "deliveries")}`, ""],
      [eur(o.total), "excl. VAT, your prices", ""],
      [holdDel ? holdDel : "0", holdDel ? (holdDel === 1 ? "delivery needs sign-off" : "deliveries need sign-off") : "sign-offs needed", holdDel ? "warn" : "good"],
      [num(co2, 0) + " kg", "CO₂e (category averages)", ""],
    ].map(([v, l, c]) => `<div class="kpi ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("")}</div>
    ${u?.note ? `<p class="fine api-note">${esc(u.note)}</p>` : ""}`;

  $("#dishes").innerHTML = `<h3>${allDirect ? "Is your request covered?" : "Can you cook every dish?"}</h3>
    <p class="muted sub">${allDirect ? "Open the request to see which product covers it." : "Open a dish to see which Valio product covers each ingredient."}</p>
    <div class="dish-grid">${ds.map(d => {
      const miss = d.gaps.filter(g => !g.optional).length;
      const badge = miss ? `<span class="badge bad">✕ ${miss} missing</span>` : d.subs.length ? `<span class="badge warn">✓ with substitute</span>`
        : (d.direct && !d.got.length) ? `<span class="badge bad">✕ not sourced</span>` : `<span class="badge ok">✓ ${d.direct ? "sourced" : "cookable"}</span>`;
      const p = state.planned[d.idx] || {};
      const meta = d.direct ? `Arrives by ${fmtDate(d.date)}${p.qty ? ` · ${num(p.qty, 1)} ${esc(p.unit || "")} requested` : ""}`
        : `${fmtDate(d.date)} · ${num(d.covers, 0)} covers${(d.diet || []).length ? " · " + d.diet.join(", ") : ""}`;
      return `<details class="dish"><summary>
        <div class="dish-top"><div class="t">${esc(d.text)}</div>${badge}</div>
        <div class="m">${meta}</div></summary>
        <div class="dish-detail">${d.got.map(({l, a}) => `<div><span>${esc(a.ingredient)} · ${qty(a.kg, cu(l))}</span><span class="p">${esc(l.name)}</span></div>`).join("")}
        ${d.gaps.map(g => `<div><span class="gap-ing">${esc(g.ingredient)}</span><span class="p">${g.optional ? "garnish, optional: not available in time" : "not available in time"}</span></div>`).join("")}
        ${!d.got.length && !d.gaps.length ? `<div><span class="p">No purchasable ingredients on this line.</span></div>` : ""}</div></details>`;
    }).join("")}</div>`;

  $("#deliveries").innerHTML = ds0.map((d, di) => {
    const ls = d.lines || [];
    return `<article class="card delivery" id="dl-${di}">
      <header class="dhead"><div class="dh-main"><div class="date">Delivery ${fmtDate(d.date)}</div>
        <div class="meta">${plural(ls.length, "product", "products")} · order by ${esc(cutoff(d))} · ${num(d.co2_kg, 0)} kg CO₂e</div></div>
        <div class="dh-side"><div class="total">${eur(d.total)}</div><span class="dstatus"></span></div></header>
      <div class="lines">${ls.map(l => lineRow(l)).join("")}</div>
      <footer class="dfoot"></footer></article>`;
  }).join("");
  ds0.forEach((d, di) => renderFoot(di));

  const gaps = o.gaps || [];
  $("#gaps").innerHTML = gaps.length ? `<div class="card gapbox"><h3>Can't be delivered in time</h3><ul>${gaps.map(g =>
    `<li><b>${esc(g.ingredient)}</b>${g.optional ? ` <span class="badge neutral">garnish</span>` : ""} (${qty(g.kg, "kg")}) for ${esc((g.dishes || []).join(", "))}: ${esc(g.why)} <span class="rule">R5</span></li>`).join("")}</ul>
    <p class="muted">The agent never drops a dish silently. Call your Valio contact or change the menu line.</p></div>` : "";
  flowFromOrder();
  renderAudit();
}
function cutoff(d) {
  const t = (d.lines || []).map(l => l.closing_time).filter(Boolean).sort()[0];
  const x = t ? new Date(t) : null;
  return x && !isNaN(x) ? x.toLocaleString("en-GB", {weekday: "short", hour: "2-digit", minute: "2-digit"}) : "the cut-off";
}

/* "Why this product": the comparison the agent made */
function whyBlock(l) {
  const opts = l.options || [];
  if (!opts.length) return "";
  const direct = isDirectLine(l), unit = cu(l);
  const cheapest = opts.reduce((m, x) => (x.cost != null && (m == null || x.cost < m.cost)) ? x : m, null);
  const chosen = opts.find(x => x.chosen) || opts[0];
  const extra = cheapest && chosen && chosen.cost != null ? chosen.cost - cheapest.cost : 0;
  const basis = opts.length === 1 ? "The only product that meets your rules and arrives in time."
    : direct ? "Direct request, so the agent took the <b>cheapest option</b> that meets your rules and arrives in time."
    : `Menu line, so the agent took the <b>best recipe fit</b> that meets your rules and arrives in time${extra > 0.005 ? `. It costs ${eur(extra)} more than the cheapest option` : ", and it is also the cheapest"}.`;
  const rel = r => r == null ? `<span class="na">no data</span>` : num(r * 100, 1) + "%";
  return `<details class="why"><summary><span class="why-t">Why this product</span><span class="why-n">${opts.length === 1 ? "only viable option" : opts.length + " options compared"}</span>
      <span class="why-basis ${direct ? "direct" : ""}">${direct ? "cheapest viable" : "best recipe fit"}</span></summary>
    <p class="why-p">${basis}</p>
    <table class="cmp"><thead><tr><th scope="col">Product</th><th scope="col">Order</th><th scope="col">Cost</th><th scope="col">€/${unit}</th><th scope="col">On-time delivery</th><th scope="col">CO₂e kg/kg</th></tr></thead>
    <tbody>${opts.map(x => `<tr class="${x.chosen ? "chosen" : ""}">
      <td data-l="Product"><span class="cmp-name">${esc(x.name)}</span>${x.chosen ? ` <span class="pick">✓ Chosen</span>` : ""}${x === cheapest && opts.length > 1 ? ` <span class="low">lowest cost</span>` : ""}${x.stock_known === false ? ` <span class="low">supplier stock</span>` : ""}</td>
      <td data-l="Order">${esc(x.units ?? "")} × ${esc(x.sales_unit || "")}</td>
      <td data-l="Cost">${x.cost != null ? eur(x.cost) : "n/a"}</td>
      <td data-l="€/${unit}">${x.per_kg != null ? eur(x.per_kg) : "n/a"}</td>
      <td data-l="On-time delivery">${rel(x.reliability)}</td>
      <td data-l="CO₂e kg/kg">${x.co2_per_kg != null ? num(x.co2_per_kg, 2) : `<span class="na">no data</span>`}</td></tr>`).join("")}</tbody></table></details>`;
}
function lineRow(l) {
  const sub = l.substitution, labels = l.labels || [], unit = cu(l);
  const al = (l.contains || []).map(a => `<span class="chip al">${esc(a)}</span>`).join("");
  const direct = isDirectLine(l);
  return `<div class="line ${l.needs_approval ? "hold" : ""}">
    <div class="l-main"><div class="pname">${esc(l.name)}</div>
      <div class="psub">${direct ? "Direct request: " : ""}${esc(l.ingredient)}${direct ? "" : " for " + esc((l.dishes || []).join(", "))}</div>
      <div class="chips">${sub ? `<span class="chip sub">${sub.type === "recipe" ? "recipe substitute" : sub.type === "valio_substitute" ? "Valio substitute" : "swapped: first choice unavailable"}</span>` : ""}
        ${al}${labels.includes("GOODS_FROM_FINLAND_BLUE_SWAN") || labels.includes("MADE_IN_FINLAND_FLAG_WITH_KEY") ? `<span class="chip">Finnish</span>` : ""}
        ${l.stock_known === false ? `<span class="chip">supplier stock</span>` : ""}${l.net_price ? `<span class="chip">your contract price</span>` : ""}</div>
      ${(l.flags || []).map(f => `<div class="flag"><span class="rule">${esc(f.rule)}</span> ${esc(f.text)}</div>`).join("")}
      ${sub && sub.why ? `<div class="psub">Why swapped: ${esc(String(sub.why).slice(0, 180))}</div>` : ""}</div>
    <div class="l-qty"><span class="lbl">Qty</span>${esc(l.units)} × ${esc(l.sales_unit)}<div class="psub">${num(l.ordered_kg, 1)} ${unit} for ${num(l.need_kg, 1)} needed</div></div>
    <div class="l-price"><span class="lbl">Unit</span>${eur(l.unit_price)}<div class="psub">${l.comparison_price != null ? eur(l.comparison_price) + "/" + unit : "per " + esc(l.sales_unit)}</div></div>
    <div class="l-total"><span class="lbl">Line</span><b>${eur(l.line_total)}</b></div>
    ${whyBlock(l)}</div>`;
}

/* approval footer per delivery */
function approvalReasons(di) {
  const d = state.order.deliveries[di], out = [];
  const limit = state.kitchens[state.order.customer]?.policy?.auto_approve_limit_eur;
  if (d.over_limit) out.push({rule: "R1", text: `Total ${eur(d.total)} is over ${limit != null ? "your " + eur0(limit) : "the"} auto-approve limit`});
  (d.lines || []).forEach(l => (l.flags || []).forEach(f => out.push({rule: f.rule, name: l.name, text: f.text})));
  (state.holds[di] || []).forEach(h => out.push({rule: "Valio", text: h}));
  if (!out.length && d.status !== "auto_approved") out.push({rule: "Policy", text: "This delivery is outside the agent's mandate"});
  return out;
}
function renderFoot(di) {
  const d = state.order.deliveries[di], box = $(`#dl-${di}`); if (!box) return;
  const foot = $(".dfoot", box), st = $(".dstatus", box), p = state.placed[di];
  if (p) {
    box.dataset.state = "placed";
    st.innerHTML = `<span class="badge ok">✓ Placed</span>`;
    foot.innerHTML = `<div class="appr placed"><div class="appr-body"><div class="appr-t">✓ Order ${esc(p.order_id || "")} placed for ${fmtDate(d.date)} at ${eur(p.total ?? d.total)}</div>
      <div class="appr-s">${p.human ? "Signed off by the head chef" : "Auto-approved by the agent within policy"}${p.note ? " · " + esc(p.note) : ""}</div></div></div>`;
    return;
  }
  if (needsApproval(di)) {
    const rs = approvalReasons(di);
    box.dataset.state = "hold";
    st.innerHTML = `<span class="badge warn">Needs sign-off</span>`;
    foot.innerHTML = `<div class="appr hold"><div class="appr-body"><div class="appr-t">The agent stopped here: ${plural(rs.length, "policy reason", "policy reasons")}</div>
      <ul class="reasons">${rs.map(r => `<li><span class="rule">${esc(r.rule)}</span><span>${r.name ? `<b>${esc(r.name)}</b>: ` : ""}${esc(r.text)}</span></li>`).join("")}</ul></div>
      <div class="appr-act"><button class="btn approve" type="button">Approve as head chef</button><div class="appr-s">Places ${eur(d.total)} for ${fmtDate(d.date)}</div></div></div>`;
  } else {
    box.dataset.state = "auto";
    st.innerHTML = `<span class="badge ok">Auto-approved</span>`;
    foot.innerHTML = `<div class="appr auto"><div class="appr-body"><div class="appr-t">✓ Within policy, no sign-off needed</div>
      <div class="appr-s">Under your auto-approve limit, no substitutes, no allergen flags. The agent places it as soon as you confirm the cart.</div></div>
      <div class="appr-act"><button class="btn primary" type="button">Confirm and place</button></div></div>`;
  }
  $(".btn", foot).onclick = e => place(di, e.currentTarget);
}
async function place(di, btn) {
  const o = state.order, d = o.deliveries[di]; btn.disabled = true;
  const human = needsApproval(di);
  try {
    const r = await api("/api/submit", {delivery: d, customer: o.customer || customer(), ...(human ? {approved_by: APPROVER} : {})});
    if (r.status === "placed") {
      state.placed[di] = {...r, human};
      (o.audit = o.audit || []).push({actor: "human", action: human ? "approve" : "confirm",
        detail: `${human ? APPROVER + " approved and placed" : "Within mandate, agent placed"} order ${r.order_id} for ${fmtDate(d.date)}, ${eur(r.total ?? d.total)}`,
        rule: human && approvalReasons(di).length ? "override" : null});
      renderFoot(di); flowFromOrder(); renderAudit(); toast(`Order ${r.order_id} placed`);
    } else if (r.status === "pending_approval") {
      // Valio's own mandate check is stricter than the draft: show its reasons and ask for the tap.
      state.holds[di] = r.holds || r.reasons || ["Valio's mandate check asks for a human sign-off"];
      renderFoot(di); flowFromOrder(); toast("Valio's mandate check asks for your sign-off.");
    } else {
      toast("Valio rejected the order: " + ((r.problems || r.reasons || []).join("; ") || r.note || "no reason given")); btn.disabled = false;
    }
  } catch (e) { toast(e.message); btn.disabled = false; }
}

/* ---------------- decision log ---------------- */
const PHASES = ["Request", "Lookup", "Order", "Approval"];
const ACTIONS = {
  submit_menu: ["Menu received", 0], read_request: ["Request understood", 0], expand_recipe: ["Recipe card written", 0],
  filter_candidates: ["Unsafe products removed", 1], match_product: ["Products ranked", 1], recipe_substitute: ["Substitute proposed", 1],
  add_to_cart: ["Added to cart", 2], gap: ["Could not source", 1], hold: ["Held for sign-off", 3], summary: ["Policy applied", 3],
  approve: ["Approved and placed", 3], confirm: ["Placed within mandate", 3],
};
const RULE_LABEL = {allergen_diet: "Guardrail", substitution: "Substitute", gap: "Gap", override: "Human override"};
const ACTORS = {agent: "Agent", guardrail: "Guardrail", policy: "Policy", human: "Head chef", kitchen: "Kitchen"};
const phaseOf = e => e.actor === "policy" || e.actor === "human" ? 3 : (ACTIONS[e.action]?.[1] ?? 1);
function auditExtra(e) {
  if (Array.isArray(e.components) && e.components.length)
    return `<div class="a-extra">${e.components.map(c => `${esc(c[0])}${c[1] != null ? ` ${num(c[1], 1)} g` : ""}`).join(" · ")} <span class="na">per portion</span></div>`;
  if (Array.isArray(e.examples) && e.examples.length)
    return `<div class="a-extra">${e.examples.map(x => `<span class="strike">${esc(x[0])}</span>: ${esc(x[1])}`).join("<br>")}</div>`;
  return "";
}
function renderAudit() {
  const a = state.order?.audit || [];
  const n = $("#audit-n"); n.textContent = a.length; n.classList.toggle("hidden", !a.length);
  if (!a.length) { $("#audit-head").innerHTML = ""; $("#audit-filters").innerHTML = ""; $("#audit").innerHTML = `<li class="audit-empty muted">Build an order to see its decision log.</li>`; return; }
  const rows = a.map((e, i) => ({e, i, ph: phaseOf(e)}));
  const filters = [["all", "Everything", rows.length], ["key", "Rules and holds", rows.filter(r => r.e.rule).length],
    ...PHASES.map((p, k) => ["p" + k, `${k + 1} ${p}`, rows.filter(r => r.ph === k).length])];
  const f = state.auditFilter;
  const shown = rows.filter(r => f === "all" || (f === "key" ? r.e.rule : r.ph === +f.slice(1)));
  const sum = [...a].reverse().find(e => e.action === "summary"), u = state.order.api_usage;
  $("#audit-head").innerHTML = `<div class="audit-sum"><b>${esc((state.order.kitchen || "").split(" (")[0])}</b>${state.order.draft_id ? ` · draft ${esc(state.order.draft_id)}` : ""}
    ${sum ? `<div>${esc(sum.detail)}</div>` : ""}${u ? `<div class="muted">Priced ${num(u.price_lookups, 0)} of ${num(u.catalogue_size, 0)} products, ${apiCalls(u)}.</div>` : ""}</div>`;
  $("#audit-filters").innerHTML = filters.map(([id, l, c]) => `<button type="button" class="fchip ${f === id ? "on" : ""}" data-f="${id}" aria-pressed="${f === id}">${esc(l)} <span>${c}</span></button>`).join("");
  $$("#audit-filters .fchip").forEach(b => b.onclick = () => { state.auditFilter = b.dataset.f; renderAudit(); });
  $("#audit").innerHTML = shown.map(({e, i, ph}) => `<li class="${esc(e.actor)}">
    <span class="a-n">${i + 1}</span>
    <div class="a-body"><div class="a-top"><span class="who">${esc(ACTORS[e.actor] || e.actor)}</span><b>${esc(ACTIONS[e.action]?.[0] || String(e.action || "").replace(/_/g, " "))}</b>
      ${e.rule ? String(e.rule).split(",").map(r => `<span class="rule">${esc(RULE_LABEL[r] || r)}</span>`).join("") : ""}<span class="a-ph">${ph + 1} ${PHASES[ph]}</span></div>
    <div class="a-detail">${esc(e.detail)}</div>${auditExtra(e)}</div></li>`).join("") || `<li class="audit-empty muted">Nothing in this filter.</li>`;
}

/* ---------------- agents tab ---------------- */
const TOOLS = [
  ["search_products", "Search the catalogue with diet tags. Products that break the kitchen's allergen rules come back as excluded, with the reason."],
  ["get_product", "Allergens (contains / may contain), claims, labels, pack size, origin, delivery reliability, CO₂e per kg, Valio's substitution links."],
  ["quote", "Customer-specific price and availability for a shortlist on a delivery date, with pack size in kg/L."],
  ["find_substitutes", "Valio's own substitution links first, then close items, filtered by the kitchen's rules and checked for delivery."],
  ["plan_menu_order", "Menu and covers in, draft order out: deliveries, per-dish allocations, gaps, approval flags and audit trail."],
  ["submit_order", "Valio re-checks the mandate; returns placed, pending_approval or rejected."],
];
$("#mcp-url").textContent = location.origin + "/mcp/";
$("#tools").innerHTML = TOOLS.map(([n, d]) => `<div class="tool"><code>${n}</code><p>${esc(d)}</p></div>`).join("");
$("#copy-mcp").onclick = () => { navigator.clipboard?.writeText(location.origin + "/mcp/"); toast("Copied"); };

/* ---------------- eval tab ---------------- */
let evalLoaded = false;
async function renderEval() {
  if (evalLoaded) return; evalLoaded = true;
  let e = null;
  for (const p of ["/eval.json", "/api/eval"]) { try { e = await api(p); if (e && e.html) break; } catch { /* try the next source */ } }
  $("#eval").innerHTML = e && e.html ? e.html : `<p class="eyebrow">Evaluation</p><h2>How we test it</h2><p class="muted">No eval results are published on this server yet.</p>`;
}

/* ---------------- boot ---------------- */
resetFlow();
$("#quick-ex").innerHTML = QUICK_EXAMPLES.map(q => `<button type="button" class="qex">${esc(q)}</button>`).join("");
$$(".qex").forEach(b => b.onclick = () => { $("#quick-text").value = b.textContent; $("#quick-text").focus(); });
(async () => {
  try {
    const r = await api("/api/kitchens");
    state.kitchens = r.kitchens || {}; state.samples = r.samples || [];
    $("#kitchen").innerHTML = Object.values(state.kitchens).map(k => `<option value="${esc(k.customer)}">${esc((k.name || k.customer).split(" (")[0])}</option>`).join("");
    $("#samples").innerHTML = state.samples.map(s => {
      const [a, ...rest] = String(s.title || s.label || s.id).split(" · ");
      return `<button type="button" class="sample" data-id="${esc(s.id)}" aria-pressed="false"><span class="s-t">${esc(a)}</span><span class="s-s">${esc(rest.join(" · "))}${rest.length ? " · " : ""}${sampleStats(s)}</span></button>`;
    }).join("");
    $$(".sample").forEach(b => b.onclick = () => loadSample(state.samples.find(s => s.id === b.dataset.id)));
    if (state.samples.length) loadSample(state.samples[0]); else { renderPolicy(); renderServices(); $("#editor").open = true; }
  } catch (e) { toast("Could not reach the server: " + e.message); }
})();
