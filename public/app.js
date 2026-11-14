const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const eur = n => "€" + Number(n || 0).toLocaleString("en-IE", {minimumFractionDigits: 2, maximumFractionDigits: 2});
const DIETS = ["vegan", "vegetarian", "gluten-free", "milk-free"];
const fmtDate = d => new Date(d + "T12:00:00").toLocaleDateString("en-GB", {weekday: "short", day: "numeric", month: "short"});

let state = {kitchens: {}, samples: [], services: [], order: null, placed: {}};

function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 3200); }

async function api(path, body) {
  const r = await fetch(path, body ? {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify(body)} : {});
  const j = await r.json().catch(() => ({error: "Server error " + r.status}));
  if (!r.ok || j.error) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}

/* ---------------- tabs ---------------- */
$$(".tab").forEach(b => b.onclick = () => {
  $$(".tab").forEach(x => x.classList.toggle("active", x === b));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + b.dataset.view));
  if (b.dataset.view === "eval") renderEval();
});

/* ---------------- kitchen & samples ---------------- */
function customer() { return $("#kitchen").value; }
function renderPolicy() {
  const k = state.kitchens[customer()]; if (!k) return;
  const p = k.policy;
  $("#policy").innerHTML = `<b>${esc(k.name)}</b><br>
    ${p.lactose_free_dairy ? "Lactose-free dairy only · " : ""}${p.free_from.length ? "Free from " + p.free_from.join(", ") + (p.strict_may_contain ? " (incl. “may contain”)" : "") + " · " : ""}
    Auto-approve up to <b>${eur(p.auto_approve_limit_eur)}</b> per delivery ·
    ${p.allow_substitutes === "same_ingredient_auto" ? "Same-ingredient swaps allowed" : "Every swap needs approval"}`;
}
function loadSample(s) {
  $$(".sample").forEach(b => b.classList.toggle("on", b.dataset.id === s.id));
  $("#kitchen").value = s.customer; renderPolicy();
  state.services = JSON.parse(JSON.stringify(s.services));
  renderServices();
}

/* ---------------- menu editor ---------------- */
function renderServices() {
  const box = $("#services"); box.innerHTML = "";
  state.services.forEach((s, si) => {
    const el = document.createElement("div"); el.className = "service";
    el.innerHTML = `<div class="service-head">
        <input type="date" value="${esc(s.date)}" aria-label="Service date">
        <input class="meal" value="${esc(s.meal || "")}" placeholder="Meal (e.g. Lunch buffet)" aria-label="Meal">
        <button class="item x" title="Remove service" aria-label="Remove service" style="display:block">×</button></div>
      <div class="items"></div><button class="add-item">+ menu line</button>`;
    $("input[type=date]", el).onchange = e => s.date = e.target.value;
    $("input.meal", el).oninput = e => s.meal = e.target.value;
    $(".service-head .x", el).onclick = () => { state.services.splice(si, 1); renderServices(); };
    const items = $(".items", el);
    s.items.forEach((it, ii) => {
      const r = document.createElement("div"); r.className = "item";
      r.innerHTML = `<input value="${esc(it.text)}" placeholder="Dish as you'd write it" aria-label="Menu line">
        <input class="covers" type="number" min="1" value="${it.covers}" aria-label="Covers">
        <button class="x" aria-label="Remove line">×</button>
        <div class="diet">${DIETS.map(d => `<span class="dchip ${it.diet?.includes(d) ? "on" : ""}" data-d="${d}">${d}</span>`).join("")}</div>`;
      $("input", r).oninput = e => it.text = e.target.value;
      $(".covers", r).oninput = e => it.covers = +e.target.value;
      $(".x", r).onclick = () => { s.items.splice(ii, 1); renderServices(); };
      $$(".dchip", r).forEach(c => c.onclick = () => {
        it.diet = it.diet || []; const d = c.dataset.d;
        it.diet = it.diet.includes(d) ? it.diet.filter(x => x !== d) : [...it.diet, d]; c.classList.toggle("on");
      });
      items.appendChild(r);
    });
    $(".add-item", el).onclick = () => { s.items.push({text: "", covers: 100, diet: []}); renderServices(); };
    box.appendChild(el);
  });
}
$("#add-service").onclick = () => { state.services.push({date: "2026-11-20", meal: "Lunch", items: [{text: "", covers: 100, diet: []}]}); renderServices(); };
$("#paste-btn").onclick = () => $("#paste-box").classList.toggle("hidden");
$("#parse-btn").onclick = async () => {
  const b = $("#parse-btn"); b.disabled = true; b.textContent = "Reading…";
  try { const r = await api("/api/parse-menu", {text: $("#paste-text").value}); state.services = r.services || []; renderServices(); $("#paste-box").classList.add("hidden"); }
  catch (e) { toast("Could not read the menu: " + e.message); }
  b.disabled = false; b.textContent = "Read menu";
};
$("#kitchen").onchange = renderPolicy;

/* ---------------- planning ---------------- */
let stepTimer;
function showWorking(on) {
  $("#working").classList.toggle("hidden", !on); $("#empty").classList.add("hidden");
  if (on) { $("#result").classList.add("hidden");
    const li = $$("#work-steps li"); li.forEach(l => l.className = ""); let i = 0; li[0].className = "now";
    clearInterval(stepTimer); stepTimer = setInterval(() => { if (i < li.length - 1) { li[i].className = "done"; i++; li[i].className = "now"; } }, 3800);
  } else clearInterval(stepTimer);
}
$("#plan-btn").onclick = async () => {
  const services = state.services.map(s => ({...s, items: s.items.filter(i => i.text.trim())})).filter(s => s.items.length);
  if (!services.length) return toast("Add at least one menu line.");
  const b = $("#plan-btn"); b.disabled = true; showWorking(true);
  try { state.order = await api("/api/plan", {services, customer: customer()}); state.placed = {}; renderOrder(); }
  catch (e) { toast("Planning failed: " + e.message); $("#empty").classList.remove("hidden"); }
  showWorking(false); b.disabled = false;
};

function dishStatus(o) {
  // per menu line: which ingredients got a product, which are gaps
  const lines = o.deliveries.flatMap(d => d.lines);
  return o.menu.map(m => {
    const got = [], subs = [];
    lines.forEach(l => l.allocations.forEach(a => { if (a.item === m.idx) { got.push({l, a}); if (l.substitution) subs.push(l); } }));
    const gaps = o.gaps.filter(g => g.alloc.some(a => a.item === m.idx));
    return {...m, got, gaps, subs};
  });
}

function renderOrder() {
  const o = state.order; $("#result").classList.remove("hidden");
  const lines = o.deliveries.flatMap(d => d.lines);
  const ds = dishStatus(o);
  const cookable = ds.filter(d => !d.gaps.filter(g => !g.optional).length).length;
  const holds = lines.filter(l => l.needs_approval).length;
  const co2 = o.deliveries.reduce((a, d) => a + d.co2_kg, 0);
  $("#summary").innerHTML = [
    [`${cookable}/${ds.length}`, "dishes fully sourced", cookable === ds.length ? "good" : "bad"],
    [lines.length, `products in ${o.deliveries.length} deliver${o.deliveries.length > 1 ? "ies" : "y"}`, ""],
    [eur(o.total), "excl. VAT, your prices", ""],
    [holds, "lines need your tap", holds ? "warn" : "good"],
    [Math.round(co2) + " kg", "CO₂e (category averages)", ""],
  ].map(([v, l, c]) => `<div class="kpi ${c}"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

  $("#dishes").innerHTML = `<h3>Can you cook every dish?</h3><p class="muted" style="margin:0">Tap a dish to see which Valio product covers each ingredient.</p>
    <div class="dish-grid">${ds.map(d => `<div class="dish" tabindex="0">
      <div class="row" style="justify-content:space-between;gap:8px"><div class="t">${esc(d.text)}</div>
      ${d.gaps.filter(g => !g.optional).length ? `<span class="badge bad">✕ ${d.gaps.filter(g => !g.optional).length} missing</span>` : d.subs.length ? `<span class="badge warn">✓ with substitute</span>` : `<span class="badge ok">✓ cookable</span>`}</div>
      <div class="m">${fmtDate(d.date)} · ${d.covers} covers${d.diet.length ? " · " + d.diet.join(", ") : ""}</div>
      <div class="dish-detail hidden">${d.got.map(({l, a}) => `<div><span>${esc(a.ingredient)} · ${a.kg.toFixed(1)} kg</span><span class="p">${esc(l.name)}</span></div>`).join("")}
      ${d.gaps.map(g => `<div><span style="color:var(--bad)">${esc(g.ingredient)}</span><span class="p">${g.optional ? "garnish, optional: not available in time" : "not available in time"}</span></div>`).join("")}</div></div>`).join("")}</div>`;
  $$(".dish").forEach(el => el.onclick = () => $(".dish-detail", el).classList.toggle("hidden"));

  $("#deliveries").innerHTML = o.deliveries.map((d, di) => {
    const flagged = d.lines.filter(l => l.needs_approval);
    return `<div class="card delivery" id="dl-${di}">
      <div class="dhead"><div><div class="date">Delivery ${fmtDate(d.date)}</div>
        <div class="meta">${d.lines.length} products · order by ${esc(cutoff(d))} · ${Math.round(d.co2_kg)} kg CO₂e</div></div>
        ${d.status === "auto_approved" ? `<span class="badge ok">Within your mandate</span>` : `<span class="badge warn">Needs your approval</span>`}
        <div class="total">${eur(d.total)}</div></div>
      <table class="lines"><tbody>${d.lines.map(l => lineRow(l)).join("")}</tbody></table>
      <div class="dfoot"><div class="note">${footNote(d, flagged)}</div>
        <button class="btn ${d.status === "auto_approved" ? "primary" : "approve"}" data-di="${di}">${d.status === "auto_approved" ? "Place order" : "Approve & place"}</button></div></div>`;
  }).join("");
  $$(".dfoot .btn").forEach(b => b.onclick = () => place(+b.dataset.di, b));

  $("#gaps").innerHTML = o.gaps.length ? `<div class="card gapbox"><h3>Can't be delivered in time</h3><ul>${o.gaps.map(g =>
    `<li><b>${esc(g.ingredient)}</b>${g.optional ? " <span class=\"badge neutral\">garnish</span>" : ""} (${g.kg} kg) for ${esc(g.dishes.join(", "))}: ${esc(g.why)}</li>`).join("")}</ul>
    <p class="muted" style="margin:0">The agent never drops a dish silently. Call your Valio contact or change the menu line.</p></div>` : "";
  renderAudit();
}
function cutoff(d) {
  const t = d.lines.map(l => l.closing_time).filter(Boolean).sort()[0];
  return t ? new Date(t).toLocaleString("en-GB", {weekday: "short", hour: "2-digit", minute: "2-digit"}) : "—";
}
function footNote(d, flagged) {
  const parts = [];
  if (d.over_limit) parts.push(`Total is over your ${eur(state.kitchens[customer()]?.policy.auto_approve_limit_eur)} auto-approve limit (R1).`);
  if (flagged.length) parts.push(`${flagged.length} line${flagged.length > 1 ? "s" : ""} flagged below.`);
  if (!parts.length) parts.push("Everything is within your rules. The agent could place this on its own.");
  return parts.join(" ");
}
function lineRow(l) {
  const sub = l.substitution;
  const al = l.contains.filter(a => a !== "milk" || true).map(a => `<span class="chip al">${esc(a)}</span>`).join("");
  return `<tr class="${l.needs_approval ? "hold" : ""}"><td><div class="pname">${esc(l.name)}</div>
    <div class="psub">${esc(l.ingredient)} for ${esc(l.dishes.join(", "))}</div>
    <div class="chips">${sub ? `<span class="chip sub">${sub.type === "recipe" ? "recipe substitute" : sub.type === "valio_substitute" ? "Valio substitute" : "swapped: first choice unavailable"}</span>` : ""}
      ${al}${l.labels.includes("GOODS_FROM_FINLAND_BLUE_SWAN") || l.labels.includes("MADE_IN_FINLAND_FLAG_WITH_KEY") ? `<span class="chip">Finnish</span>` : ""}
      ${l.stock_known ? "" : `<span class="chip">supplier stock</span>`}${l.net_price ? `<span class="chip">your contract price</span>` : ""}</div>
    ${l.flags.map(f => `<div class="flag">⚑ ${esc(f.rule)} · ${esc(f.text)}</div>`).join("")}
    ${sub && sub.why ? `<div class="psub">Why: ${esc(sub.why).slice(0, 160)}</div>` : ""}</td>
    <td class="qty">${l.units} ${esc(l.sales_unit)}<div class="psub">${l.ordered_kg.toFixed(1)} kg/L for ${l.need_kg.toFixed(1)} needed</div></td>
    <td class="money">${eur(l.unit_price)}<div class="psub">/${esc(l.sales_unit)}</div></td>
    <td class="money"><b>${eur(l.line_total)}</b></td></tr>`;
}
async function place(di, btn) {
  const d = state.order.deliveries[di]; btn.disabled = true;
  try {
    let r = await api("/api/submit", {delivery: d, customer: customer()});
    if (r.status === "pending_approval") r = await api("/api/submit", {delivery: d, customer: customer(), approved_by: "Head chef (one-tap approval)"});
    if (r.status === "placed") {
      state.order.audit.push({actor: "human", action: "approve", detail: `${r.approved_by} placed order ${r.order_id} for ${fmtDate(d.date)}, ${eur(r.total)}`, rule: r.holds_overridden?.length ? "override" : null});
      $(`#dl-${di} .dfoot`).innerHTML = `<div class="placed">✓ Order ${esc(r.order_id)} placed for ${fmtDate(d.date)} · ${eur(r.total)}</div><div class="note" style="margin-left:auto">${esc(r.note)}</div>`;
      renderAudit(); toast(`Order ${r.order_id} placed`);
    } else { toast("Valio rejected the order: " + (r.problems || []).join("; ")); btn.disabled = false; }
  } catch (e) { toast(e.message); btn.disabled = false; }
}

/* ---------------- audit ---------------- */
function renderAudit() {
  const a = state.order?.audit || [];
  $("#audit").innerHTML = a.map(e => `<li class="${esc(e.actor)}"><span class="who">${esc(e.actor)}</span>${esc(e.detail)}${e.rule ? `<span class="rule">${esc(e.rule)}</span>` : ""}</li>`).join("");
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
  let e; try { e = await api("/eval.json"); } catch { $("#eval").innerHTML = "<p>No eval results published yet.</p>"; return; }
  $("#eval").innerHTML = e.html || "";
}

/* ---------------- boot ---------------- */
(async () => {
  const r = await api("/api/kitchens");
  state.kitchens = r.kitchens; state.samples = r.samples;
  $("#kitchen").innerHTML = Object.values(r.kitchens).map(k => `<option value="${k.customer}">${esc(k.name.split(" (")[0])}</option>`).join("");
  $("#samples").innerHTML = r.samples.map(s => `<button class="sample" data-id="${s.id}">${esc(s.label)}</button>`).join("");
  $$(".sample").forEach(b => b.onclick = () => loadSample(r.samples.find(s => s.id === b.dataset.id)));
  loadSample(r.samples[0]);
})();
