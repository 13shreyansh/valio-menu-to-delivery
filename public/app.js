/* Valio's account portal. All order numbers, prices and decisions come from the server. */
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icon = (name, cls = "") =>
  `<svg class="icon ${cls}" aria-hidden="true"><use href="/icons.svg#${name}"></use></svg>`;
const money = (v) =>
  new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" }).format(
    v || 0,
  );
const date = (v, long = false) =>
  v
    ? new Date(v.length === 10 ? v + "T12:00:00" : v).toLocaleDateString(
        "en-GB",
        {
          weekday: long ? "long" : "short",
          day: "numeric",
          month: "short",
          timeZone: "Europe/Helsinki",
        },
      )
    : "To confirm";
const time = (v) =>
  v
    ? new Date(typeof v === "number" ? v * 1000 : v).toLocaleTimeString(
        "en-GB",
        { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Helsinki" },
      )
    : "Time to confirm";
const btn = (label, action, cls = "", attrs = "") =>
  `<button class="${cls}" data-action="${action}" ${attrs}>${label}</button>`;
let S = {
  account: null,
  order: null,
  path: location.pathname,
  drawer: null,
  error: "",
  busy: false,
  working: false,
  steps: [],
  request: "",
  input: "",
  question: "",
  filter: "all",
  tab: "Placed",
  catalogue: [],
  catalogueQuery: "",
  catalogueLoaded: false,
  readOrder: null,
  bell: false,
  menu: false,
  editing: false,
  media: null,
  mediaName: "",
  listening: false,
  level: 0,
  notice: "",
};
const nav = [
  ["Dashboard", "/dashboard", "layout-dashboard"],
  ["Orders", "/orders", "clipboard-list"],
  ["Catalogue", "/catalogue", "search"],
  ["Deliveries", "/deliveries", "truck"],
  ["Invoices", "/invoices", "receipt"],
  ["Settings", "/settings/rules", "settings"],
];
async function api(path, body) {
  const r = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let data;
  try {
    data = await r.json();
  } catch {
    throw Error("Valio could not finish that check. Try again.");
  }
  if (!r.ok) throw Error(data.error || "Valio is unavailable. Try again.");
  return data;
}
async function task(fn) {
  if (S.busy) return false;
  S.busy = true;
  S.error = "";
  render();
  try {
    await fn();
    return true;
  } catch (e) {
    S.error = e.message;
    return false;
  } finally {
    S.busy = false;
    render();
  }
}
function navigate(path) {
  S.notice = "";
  S.path = path;
  S.error = "";
  S.bell = false;
  S.menu = false;
  S.readOrder = null;
  history.pushState({}, "", path);
  render();
  window.scrollTo(0, 0);
  if (
    path === "/orders" ||
    path === "/dashboard" ||
    path === "/deliveries" ||
    path === "/invoices"
  )
    refreshAccount();
  if (path === "/catalogue" && !S.catalogueLoaded) loadCatalogue();
}
async function refreshAccount() {
  try {
    S.account = await api("/account");
    if (
      !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
    )
      render();
  } catch (e) {
    S.error = e.message;
    render();
  }
}
async function ensureDraft() {
  const id = localStorage.getItem("aurora-draft");
  if (id) {
    try {
      S.order = await api("/drafts/" + id);
      return;
    } catch {
      localStorage.removeItem("aurora-draft");
    }
  }
  S.order = await api("/drafts", {});
  localStorage.setItem("aurora-draft", S.order.draft_id);
}
async function boot() {
  if (S.path === "/") {
    render();
    return;
  }
  render();
  try {
    S.account = await api("/account");
    await ensureDraft();
    render();
    if (S.path === "/catalogue") loadCatalogue();
    if (S.path.startsWith("/orders/draft-")) {
      S.order = await api("/drafts/" + S.path.slice("/orders/draft-".length));
      localStorage.setItem("aurora-draft", S.order.draft_id);
      render();
    }
    if (S.path.startsWith("/orders/AU-")) {
      const saved = S.account.orders.find((o) =>
        S.path.endsWith(o.order_number),
      );
      if (saved?.draft_id) {
        S.readOrder = await api("/drafts/" + saved.draft_id);
        render();
      }
    }
  } catch (e) {
    S.error = e.message;
    S.path = "/";
    history.replaceState({}, "", "/");
    render();
  }
}
function table(head, rows, cls = "") {
  return `<div class="table-wrap"><table class="table ${cls}"><thead><tr>${head.map((h, i) => `<th class="${/Total|price/.test(h) ? "money" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td colspan="${head.length}" class="empty">No orders in this view.</td></tr>`}</tbody></table></div>`;
}
function start() {
  return `<div class="start"><section class="card signin"><div class="wordmark">Valio Aimo</div><h2>Sign in to order for your kitchen</h2>${btn("Continue with company account", "company", "primary")}${S.companyNote ? `<p class="note">Company sign-in is set up by your Valio contact</p>` : ""}<hr>${btn("Try the demo account (Hotel Aurora)", "login", "link")}<footer class="tiny">Prices and stock come live from Valio's system.</footer>${S.error ? `<p class="error" role="alert">${esc(S.error)}</p>` : ""}</section></div>`;
}
function title() {
  if (S.readOrder) return "Order " + S.readOrder.order_number;
  if (S.path.startsWith("/orders/"))
    return S.path.includes("confirmation")
      ? "Order confirmation"
      : "Order for week 47";
  if (S.path.startsWith("/settings")) return "Settings";
  return nav.find((n) => n[1] === S.path)?.[0] || "Dashboard";
}
function render() {
  if (S.path === "/") {
    $("#app").innerHTML = start();
    document.body.className = "";
    return;
  }
  const active = S.path.startsWith("/settings")
    ? "/settings/rules"
    : S.path.startsWith("/orders")
      ? "/orders"
      : S.path;
  document.body.className =
    (S.drawer ? "has-drawer " : "") +
    (S.drawer === "receipt" ? "has-receipt" : "");
  $("#app").innerHTML =
    `<aside class="sidebar ${S.menu ? "open" : ""}"><div class="brand"><div class="wordmark">Valio Aimo</div><div class="tiny">${esc(S.account?.name || "Hotel Aurora")}</div></div><nav>${nav.map(([label, path, ic]) => `<a class="nav-item ${active === path ? "current" : ""}" href="${path}" data-nav="${path}">${icon(ic, "nav-icon")}${label}</a>`).join("")}</nav>${S.accountMenu ? btn(icon("log-out") + "Sign out", "logout", "ghost") : ""}<button class="account-row" data-action="account-menu"><span class="avatar">SV</span><span>Sanna Virtanen<span class="tiny" style="display:block">Head chef</span></span></button></aside><div class="workspace"><header class="topbar"><h1>${esc(title())}</h1><span class="wordmark mobile-brand">Valio Aimo</span><div class="top-actions">${btn(icon("mic") + '<span class="ask-label">Ask Valio</span>', "ask", "secondary ask-open", 'aria-label="Ask Valio"')}${btn(icon("bell") + (unread() ? '<i class="unread"></i>' : ""), "bell", "icon-btn bell", 'aria-label="Account events"')}${btn(icon("menu"), "menu", "icon-btn mobile-menu", 'aria-label="Open menu"')}</div></header><main><h1 class="mobile-title">${esc(title())}</h1>${S.error ? `<div role="alert" class="error">${esc(S.error)}</div>` : ""}${!S.order || !S.account ? '<div class="skeleton" aria-label="Loading account"><div class="skeleton-line"></div><div class="skeleton-line"></div></div>' : page()}</main>${footer()}</div>${S.drawer ? drawer() : ""}${S.bell ? events() : ""}${S.why ? why() : ""}${S.invoice ? invoice() : ""}`;
}
function unread() {
  return S.account?.events.some(
    (e) =>
      !JSON.parse(localStorage.getItem("aurora-read") || "[]").includes(e.id),
  );
}
function page() {
  if (S.readOrder) return orderPage(S.readOrder, true);
  if (S.path.includes("confirmation")) return confirmation();
  if (S.path === "/dashboard") return dashboard();
  if (S.path === "/orders") return ordersPage();
  if (S.path.startsWith("/orders/"))
    return orderPage(S.order, S.order.status === "placed");
  if (S.path === "/catalogue") return catalogue();
  if (S.path === "/deliveries") return deliveries();
  if (S.path === "/invoices") return invoices();
  if (S.path.startsWith("/settings")) return settings();
  return dashboard();
}
function budget(o) {
  const max = Math.max(o.total, o.budget) * 1.04,
    limit = (o.budget / max) * 100;
  return `<div class="budget" aria-label="${money(o.total)} of ${money(o.budget)} weekly budget"><i class="budget-fill" style="width:${(Math.min(o.total, o.budget) / max) * 100}%"></i><i class="budget-over" style="width:${(Math.max(0, o.total - o.budget) / max) * 100}%"></i><i class="budget-tick" style="left:${limit}%"></i></div>`;
}
const stageNames = [
  "Reading your recipes",
  "Scaling to 120 guests",
  "Checking stock at Valio",
  "Comparing pack sizes and prices",
  "Checking allergens",
  "Checking your budget",
];
function checklistLabel(i, event) {
  if (i === 1)
    return event.covers
      ? `Scaling to ${event.covers} guests`
      : S.steps[1]?.label || "Scaling your recipes";
  if (i === 2) {
    const day = event.date
      ? new Date(event.date + "T12:00:00").toLocaleDateString("en-GB", {
          weekday: "long",
        })
      : "delivery";
    return `Checking ${day} stock at Valio`;
  }
  if (i === 4)
    return (
      "Checking allergens: " +
      (S.account.rules.allergens
        .filter(
          (a) => a !== "peanuts" || !S.account.rules.allergens.includes("nuts"),
        )
        .map((a) => "no " + a)
        .join(", ") || "your kitchen rules")
    );
  return stageNames[i];
}
function checklist() {
  return `<div class="checklist" aria-live="polite">${S.steps.map((s, i) => `<div class="checklist-row" data-stage="${i}">${s.done ? (s.attention ? '<i class="attention-dot"></i>' : icon("check", "green")) : '<i class="spinner"></i>'}<span>${esc(s.label)}</span><span class="result ${s.attention ? "amber" : ""}">${esc(s.result)}</span></div>`).join("")}</div>`;
}
function deliveryMini(d) {
  return `<div class="delivery-mini"><span>${date(d.date)}</span><span class="muted">· arrival time to confirm · ${d.rows.filter((r) => r.units > 0).length} products ·</span><span>${money(d.subtotal)}</span></div>`;
}
function dashboard() {
  const o = S.order;
  const today = new Date();
  const stamp = today.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Europe/Helsinki",
  });
  const pending = o.pending;
  const heading = S.working
    ? "Updating next week's order"
    : o.status === "placed"
      ? "Next week's order is placed"
      : pending
        ? `Next week's order needs ${pending} OKs`
        : "Next week's order is ready";
  return `<div class="subline">${stamp} · ordering for week 47</div><div class="dashboard-grid"><section class="card order-card"><div class="between"><h2>${heading}</h2><span class="pill ${S.working ? "" : pending ? "warn" : "ok"}">${S.working ? "Updating…" : o.status === "placed" ? "Placed" : pending ? `${pending} to approve` : "Ready to send"}</span></div><p class="prepared">Prepared from your menu, ${S.account.bookings.reduce((n, b) => n + b.covers, 0)} bookings and current stock.</p><p class="totals"><span data-total="${o.total}">${o.rows.filter((r) => r.units > 0).length} products · ${o.deliveries.length} deliveries · <span id="animated-total">${money(o.total)}</span></span> of your ${money(o.budget)} weekly budget</p>${budget(o)}${S.working ? checklist() : o.deliveries.map(deliveryMini).join("")}${o.request && !S.working ? `<p class="change-summary">${summary(o)}</p>` : ""}<div class="row order-actions">${btn("Review order", "review", "primary", S.working ? "disabled" : "")}${btn("Change something", "ask", "ghost", o.status === "placed" ? "disabled" : "")}</div></section><section class="card summary-card"><h3>This week and month</h3>${summaryRows(o)}</section></div><section class="recent"><h3>Recent orders</h3>${orderTable(S.account.orders.slice(0, 5), true)}</section>`;
}
function eventName(label, day) {
  const weekday = day
    ? new Date(day + "T12:00:00").toLocaleDateString("en-GB", {
        weekday: "long",
      })
    : "";
  const name = String(label || "Wedding").replace(
    new RegExp("^" + weekday + "\\s+", "i"),
    "",
  );
  return /^(wedding|conference)$/i.test(name)
    ? name[0].toUpperCase() + name.slice(1).toLowerCase()
    : name;
}
function summary(o) {
  const n = o.rows.filter((r) => r.change && r.units > 0).length;
  const delta = o.total - (o.previous_total ?? o.baseline_total);
  return `${delta >= 0 ? "Added" : "Removed"} ${n} products for ${o.wedding ? new Date(o.wedding.date + "T12:00:00").toLocaleDateString("en-GB", { weekday: "long" }) + " " + esc(eventName(o.wedding.event, o.wedding.date).toLowerCase()) : "your kitchen change"} (${delta >= 0 ? "+" : "−"}${money(Math.abs(delta))}).`;
}
function summaryRows(o) {
  const cuts = o.deliveries
    .map((d) => d.cutoff)
    .filter(Boolean)
    .sort();
  const cut = cuts[0];
  const left = cut ? Math.max(0, new Date(cut) - Date.now()) : 0;
  const spent = S.account.orders
    .filter((r) => r.placed_at.startsWith("2026-11"))
    .reduce((n, r) => n + r.total, 0);
  return `<div class="summary-row"><span>Order by</span><span>${cut ? `${date(cut).split(" ")[0]} ${time(cut)}<br><span class="tiny">${Math.floor(left / 3600000)} h ${Math.floor((left % 3600000) / 60000)} min left</span>` : "To confirm"}</span></div><div class="summary-row"><span>First delivery</span><span>${date(o.deliveries[0]?.date)}<br><span class="tiny">Arrival time to confirm</span></span></div><div class="summary-row"><span>Spent in November</span><span>${money(spent)} of ${money(o.rules.monthly_limit)}</span></div><div class="summary-row"><span>Left this month</span><span>${money(Math.max(0, o.rules.monthly_limit - spent))}</span></div>`;
}
function orderTable(rows, recent = false) {
  return table(
    recent
      ? ["Order no.", "Placed by", "Delivered", "Products", "Total", "Note"]
      : [
          "Order no.",
          "Placed by",
          "Placed at",
          "Deliveries",
          "Total",
          "Status",
        ],
    rows
      .map(
        (o) =>
          `<tr class="clickable ${Date.now() - new Date(o.placed_at) < 3000 ? "new-order" : ""}" ${o.status === "Draft" ? `data-open-draft="${esc(o.draft_id)}"` : `data-open-order="${esc(o.order_number)}"`} tabindex="0"><td><a href="/orders/${o.status === "Draft" ? "draft-" + esc(o.draft_id) : esc(o.order_number)}" ${o.status === "Draft" ? `data-open-draft="${esc(o.draft_id)}"` : `data-open-order="${esc(o.order_number)}"`}>${esc(o.order_number)}</a></td><td><span class="placed-by">${o.placed_by === "Aurora Group assistant" ? icon("plug") : ""}${esc(o.placed_by)}</span>${o.placed_by === "Aurora Group assistant" ? (o.status === "Draft" ? '<span class="tiny">Prepared by Aurora Group assistant</span>' : '<span class="tiny">Placed by Aurora Group assistant · Within your rules</span>') : ""}</td><td>${recent ? (o.status === "Delivered" ? date(o.deliveries[o.deliveries.length - 1]?.date) : "Not delivered") : date(o.placed_at)}${recent ? "" : `<span class="tiny">${time(o.placed_at)}</span>`}</td><td>${recent ? o.products : o.deliveries.length}</td><td class="money">${money(o.total)}</td><td>${recent ? "" : `<span class="pill ${o.status === "Delivered" ? "" : "ok"}">${esc(o.status)}</span>`}</td></tr>`,
      )
      .join(""),
  );
}
function ordersPage() {
  const rows =
    S.tab === "Drafts"
      ? S.account.drafts ||
        (S.order.status === "draft"
          ? [
              {
                ...S.order,
                order_number: "Week 47",
                placed_by: "Sanna Virtanen",
                placed_at: S.order.quote_at,
                status: "Draft",
                products: S.order.rows.length,
              },
            ]
          : [])
      : S.account.orders.filter((o) => o.status === S.tab);
  return `<div class="tabs">${["Drafts", "Placed", "Delivered"].map((t) => btn(t, "order-tab", S.tab === t ? "active" : "", `data-value="${t}"`)).join("")}</div>${orderTable(rows)}`;
}
function approvalTitle(c, o) {
  if (c.kind === "swap") {
    const r = o.rows.find((r) => c.row_ids.includes(r.id));
    return `Swap salmon for ${esc(r?.name || "the available fish")}`;
  }
  if (c.kind === "pack") {
    const r = o.rows.find((r) => c.row_ids.includes(r.id));
    return `Buy cream as ${r?.units} × ${r?.pack} L packs`;
  }
  if (c.id === "budget")
    return `${money(o.total - o.budget)} over your ${money(o.budget)} weekly limit`;
  return esc(c.text);
}
function approval(c, o) {
  if (c.approved)
    return `<div class="approval approved" data-check="${esc(c.id)}">${icon("check")}<span class="approval-copy">${approvalTitle(c, o)}: approved by Sanna · ${esc(c.approved_at)}</span>${btn("Undo", "unapprove", "link", `data-value="${esc(c.id)}"`)}</div>`;
  return `<div class="approval" data-check="${esc(c.id)}">${icon(c.kind === "swap" ? "repeat-2" : c.kind === "pack" ? "package" : c.kind === "budget" ? "wallet" : "circle-alert")}<div class="approval-copy"><div class="approval-title">${approvalTitle(c, o)}</div><p>${esc(c.text)}</p>${c.reopened ? '<p class="reopened">You changed the quantity, so please check this again.</p>' : ""}</div><div class="approval-buttons">${c.kind === "gap" ? btn(c.row_ids.length ? "Restore quantity" : "Change menu", c.row_ids.length ? "restore" : "ask", "secondary", `data-value="${esc(c.row_ids[0] || "")}"`) : btn(c.kind === "budget" ? "Change order" : "Keep original", c.kind === "pack" ? "small-cream" : c.kind === "swap" ? "keep-original" : "change-order", "ghost")}${c.can_approve ? btn(c.kind === "budget" ? "Approve once" : "Approve", "approve", "primary", `data-value="${esc(c.id)}" ${S.busy ? "disabled" : ""}`) : ""}</div></div>`;
}
function eventTag(o) {
  return o.wedding
    ? "For " +
        new Date(o.wedding.date + "T12:00:00").toLocaleDateString("en-GB", {
          weekday: "long",
        }) +
        " " +
        eventName(o.wedding.event, o.wedding.date).toLowerCase()
    : "For kitchen change";
}
function orderPage(o, readonly = false) {
  const count = o.rows.filter((r) => r.units > 0).length;
  const changed = o.rows.filter((r) => r.change).length;
  return `<div class="subline"><span>${o.deliveries.length} deliveries · ${count} products · ${readonly ? "Placed " + date(o.placed_at) : "Not sent to Valio yet"}</span>${btn("How this was decided", "receipt", "secondary")}</div>${!readonly && o.checks.length ? `<section class="approvals"><h3>Needs your OK (${o.pending})</h3><div class="approval-box">${o.checks.map((c) => approval(c, o)).join("")}</div></section>` : ""}${!readonly ? `<div class="filter" aria-label="Order products">${btn(`Changed (${changed})`, "filter", S.filter === "changed" ? "active" : "", 'data-value="changed"')}${btn(`All (${count})`, "filter", S.filter === "all" ? "active" : "", 'data-value="all"')}</div>` : '<div style="height:16px"></div>'}${o.deliveries
    .map((d) => {
      const rows = d.rows.filter(
        (r) => readonly || S.filter === "all" || r.change,
      );
      if (!rows.length) return "";
      return `<section class="delivery-section"><div class="day-header"><div><h3>${date(d.date, true)} · ${o.historical ? "delivered" : "arrival time to confirm"}</h3><p>${d.cutoff ? "Order by " + date(d.cutoff) + " " + time(d.cutoff) : o.historical ? "Order-by time was not recorded" : "Order-by time to confirm"}</p></div><span>${money(d.subtotal)}</span></div>${table(["Product", "Quantity", "Unit price", "Total", ""], rows.map((r) => `<tr data-row="${esc(r.id)}"><td class="product"><div class="product-name">${esc(r.name)}</div><span class="tiny">${r.pack} ${esc(r.unit)} · <span class="product-code">${esc(r.product_id)}</span>${r.previous_units !== null && r.previous_units !== undefined && r.previous_units !== r.units ? `<span class="was"><s>was ${r.previous_units}</s></span>` : ""}</span>${r.change ? `<span class="tag">${r.change === "Swapped" ? esc(r.change_reason) : esc(eventTag(o))}</span>` : ""}</td><td>${readonly ? r.units : `<div class="stepper">${btn("−", "qty", "", `aria-label="Less ${esc(r.name)}" data-row-id="${esc(r.id)}" data-units="${r.units - 1}" ${S.busy || r.units === 0 ? "disabled" : ""}`)}<span>${r.units}</span>${btn("+", "qty", "", `aria-label="More ${esc(r.name)}" data-row-id="${esc(r.id)}" data-units="${r.units + 1}" ${S.busy ? "disabled" : ""}`)}</div>`}</td><td class="money unit-price">${money(r.unit_price)}</td><td class="money">${money(r.total)}</td><td>${btn("Why?", "why", "link why " + (!r.change ? "unchanged" : ""), `data-value="${esc(r.id)}"`)}</td></tr>`).join(""), "order-table")}</section>`;
    })
    .join("")}`;
}
function footer() {
  if (
    !S.order ||
    !S.account ||
    S.readOrder ||
    !S.path.startsWith("/orders/") ||
    S.path.includes("confirmation") ||
    S.order.status === "placed"
  )
    return "";
  const o = S.order;
  return `<div class="footer-bar"><div class="footer-total">Total ${money(o.total)}${o.total > o.budget ? `<span class="amber">${money(o.total - o.budget)} over weekly budget</span>` : ""}</div><div class="row">${o.pending ? `<span class="small muted">${o.pending} still need your OK</span>` : ""}${btn(S.busy ? "Checking…" : "Place order", "place", "primary", !o.can_place || S.busy || S.rulesSaving ? "disabled" : "")}</div></div>`;
}
function confirmation() {
  const o = S.order;
  return `<section class="card confirmation">${icon("circle-check")}<h1>Order sent to Valio</h1><p class="muted">Order ${esc(o.order_number || o.confirmation?.order_number)}</p><div class="deliveries">${o.deliveries.map(deliveryMini).join("")}</div><p>You'll get a confirmation from Valio by email.</p><div class="row" style="margin-top:24px">${btn("View orders", "orders", "primary")}${btn("Dashboard", "dashboard", "ghost")}</div><p class="tiny">Demo account: no real order was placed.</p></section>`;
}
function catalogue() {
  return `<form class="search-form" id="catalogue-search"><input name="q" aria-label="Search products or codes" placeholder="Search products or codes" value="${esc(S.catalogueQuery)}">${btn("Search", "search", "secondary", S.busy ? "disabled" : "")}</form>${!S.catalogueLoaded ? '<div class="skeleton" aria-label="Loading catalogue"></div>' : table(["Product", "Pack", "Code", "Price per pack", "Per kg/L", "Stock date", ""], S.catalogue.map((p) => `<tr><td>${esc(p.name_fi || p.name)}</td><td>${p.pack || "—"} ${esc(p.pack_dim || p.sales_unit)}</td><td class="product-code">${esc(p.id)}</td><td class="money">${money(p.unit_price)}</td><td class="money">${p.comparison_price ? money(p.comparison_price) : "—"}</td><td>${date(p.availability.available_date)}<span class="tiny">${p.allowed ? "Available" : "Not within your rules or cut-off"}</span></td><td>${btn("Add to order", "add", "secondary", `data-value="${esc(p.id)}" ${!p.allowed || S.busy ? "disabled" : ""}`)}</td></tr>`).join(""))}${S.notice ? `<p class="status-note" role="status">${esc(S.notice)}</p>` : ""}`;
}
function deliveries() {
  const placed = S.account.orders.filter((o) => o.status === "Placed");
  const ds = placed.flatMap((o) =>
    o.deliveries.map((d) => ({ ...d, order: o.order_number })),
  );
  const rows = ds.length
    ? ds
    : S.order.deliveries.map((d) => ({ ...d, order: "Week 47 · Not placed" }));
  return table(
    ["Day", "Arrival time", "Order by", "Products", "Total", "Order"],
    rows
      .map(
        (d) =>
          `<tr><td>${date(d.date, true)}</td><td>To confirm</td><td>${d.cutoff ? date(d.cutoff) + " " + time(d.cutoff) : "Order-by time to confirm"}</td><td>${d.rows.length}</td><td class="money">${money(d.subtotal)}</td><td>${esc(d.order)}</td></tr>`,
      )
      .join(""),
  );
}
function invoices() {
  return table(
    ["Month", "Total", ""],
    S.account.orders
      .filter((o) => o.historical)
      .map(
        (o) =>
          `<tr><td>${new Date(o.placed_at).toLocaleDateString("en-GB", { month: "long", year: "numeric" })}<span class="tiny">${esc(o.order_number)}</span></td><td class="money">${money(o.total)}</td><td>${btn("View", "invoice", "link", `data-value="${esc(o.order_number)}"`)}</td></tr>`,
      )
      .join(""),
  );
}
function settings() {
  const section = S.path.split("/")[2] || "rules";
  return `<div class="settings-layout"><nav class="settings-nav" aria-label="Settings">${[
    ["rules", "Ordering rules"],
    ["team", "Team"],
    ["connected-ai", "Connected assistants"],
    ["kitchen", "Kitchen profile"],
  ]
    .map(
      ([id, name]) =>
        `<a href="/settings/${id}" data-nav="/settings/${id}" class="${section === id ? "current" : ""}">${name}</a>`,
    )
    .join(
      "",
    )}</nav><div class="settings-content">${section === "rules" ? rulesView() : section === "connected-ai" ? connected() : section === "team" ? team() : kitchenProfile()}</div></div>`;
}
function rulesView() {
  const r = S.account.rules;
  const stamp = `Changed by ${esc(r.changed_by)}, ${new Date(r.changed_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`;
  const row = (label, control) =>
    `<div class="rule-row"><label>${label}<span class="tiny">${stamp}</span></label>${control}</div>`;
  return `<section class="rule-section"><h3>Budget</h3>${row("Weekly limit", `<div class="row"><span>€</span><input type="number" min="1" step=".01" aria-label="Weekly limit" data-rule="weekly_limit" value="${r.weekly_limit}"></div>`)}${row("When an order goes over", `<select aria-label="When an order goes over" data-rule="over_limit"><option value="ask" ${r.over_limit === "ask" ? "selected" : ""}>Ask me first</option><option value="block" ${r.over_limit === "block" ? "selected" : ""}>Don't allow</option></select>`)}</section><section class="rule-section"><h3>Swaps</h3>${row("Ask me before any product swap", `<input class="toggle" type="checkbox" aria-label="Ask me before any product swap" data-rule="ask_swap" ${r.ask_swap ? "checked" : ""}>`)}${row("Only swap to products with the same or fewer allergens", `<input class="toggle" type="checkbox" aria-label="Only swap to products with the same or fewer allergens" data-rule="same_allergens" ${r.same_allergens ? "checked" : ""}>`)}</section><section class="rule-section"><h3>Allergens</h3><div class="chips">${r.allergens
    .filter((a) => a !== "peanuts")
    .map((a) => `<span class="chip">No ${esc(a)} (whole kitchen)</span>`)
    .join("")}</div>${
    S.addAllergen
      ? `<select id="new-allergen" aria-label="Choose allergen">${[
          "milk",
          "egg",
          "fish",
          "gluten",
          "sesame",
          "soy",
          "celery",
          "mustard",
          "crustaceans",
          "molluscs",
          "sulphites",
          "lupin",
        ]
          .filter((a) => !r.allergens.includes(a))
          .map((a) => `<option>${a}</option>`)
          .join("")}</select> ${btn("Add", "allergen-confirm", "secondary")}`
      : btn("Add allergen", "allergen", "secondary")
  }</section><section class="rule-section"><h3>Bigger changes</h3>${row("Ask me when an order grows by more than", `<div class="row"><span>€</span><input type="number" min="1" step=".01" aria-label="Ask me when an order grows by more than" data-rule="growth_limit" value="${r.growth_limit}"></div>`)}</section><section class="rule-section"><h3>Who can order</h3>${S.account.team.map((t) => `<div class="rule-row"><span>${esc(t.name)}<span class="tiny" style="display:block">${esc(t.role)}</span></span><span class="small muted">${esc(t.permission)}</span></div>`).join("")}</section><p class="small muted">These rules apply to every order from your account, including ones made by a connected AI.</p>${S.notice ? `<p class="status-note" role="status">${esc(S.notice)}</p>` : ""}`;
}
function connected() {
  const last = S.account.events.find((e) => e.by === "Aurora Group assistant");
  return `<h2>Connect your own AI assistant</h2><p class="muted" style="margin-top:12px">Use Claude, ChatGPT or your company's own assistant to order from Valio. It follows the same ordering rules as your team.</p><div class="copy-row"><input readonly aria-label="MCP address" value="${esc(S.account.mcp_url)}">${btn(icon("copy") + "Copy", "copy", "secondary")}</div><h3>Claude</h3><ol class="steps"><li>Open Settings → Connectors → Add custom connector.</li><li>Name it Valio Aimo and paste the MCP address above.</li><li>Connect, then ask for dishes, guests and a delivery day.</li></ol><h3>ChatGPT</h3><ol class="steps"><li>Open Settings → Apps and enable developer mode in advanced settings.</li><li>Create an app with the MCP address above and no authentication.</li><li>Add it to a chat and ask for your kitchen's order.</li></ol><h3>Connected</h3><div class="connected-row">Aurora Group assistant<span class="tiny" style="display:block">${last ? "Last used " + time(last.at) : "Ready to connect"}</span></div>${S.notice ? `<p class="status-note" role="status">${esc(S.notice)}</p>` : ""}`;
}
function team() {
  return `<h2>Team</h2><div style="height:20px"></div>${table(["Name", "Role", "Permission"], S.account.team.map((t) => `<tr><td>${esc(t.name)}</td><td>${esc(t.role)}</td><td>${esc(t.permission)}</td></tr>`).join(""))}`;
}
function kitchenProfile() {
  return `<h2>Hotel Aurora</h2><p class="muted" style="margin-top:12px">Helsinki · Customer HC-1001</p><p class="small muted" style="margin-top:16px">Hotel Aurora is a sample kitchen account. Its menus, recipes, bookings, stock and past quantities are account records. Product names, prices, availability and cut-offs come from Valio.</p><section class="card"><h3>Bookings</h3>${S.account.bookings.map((b) => `<div class="summary-row"><span>${date(b.date)}</span><span>${b.covers} guests</span></div>`).join("")}</section><section class="card"><h3>Recipes and menu</h3>${Object.entries(
    S.account.recipes,
  )
    .map(
      ([key, r]) =>
        `<details style="margin-top:12px"><summary>${esc(r.name)}</summary>${Object.entries(
          r.ingredients,
        )
          .map(
            ([name, amount]) =>
              `<p class="small muted">${esc(name)} · ${amount} g/ml per guest</p>`,
          )
          .join("")}</details>`,
    )
    .join(
      "",
    )}</section><section class="card"><h3>Current stock</h3>${Object.entries(
    S.account.stock,
  )
    .map(
      ([name, n]) =>
        `<div class="summary-row"><span>${esc(name.replace("_", " "))}</span><span>${n} kg/L</span></div>`,
    )
    .join("")}</section>`;
}
function events() {
  return `<section class="popover events" aria-label="Account events"><h3>Account events</h3>${
    S.account.events.length
      ? S.account.events
          .slice(0, 10)
          .map(
            (e) =>
              `<div class="event">${esc(e.text)}<p class="small muted">${money(e.total)} · ${esc(e.note)}</p><span class="tiny">${date(e.at)} · ${time(e.at)}</span></div>`,
          )
          .join("")
      : '<p class="muted" style="margin-top:12px">Orders and account changes will appear here.</p>'
  }</section>`;
}
function drawer() {
  return S.drawer === "receipt"
    ? receipt()
    : `<aside class="drawer" role="complementary" aria-label="Ask Valio"><header class="drawer-header"><h3>Ask Valio</h3>${btn(icon("x"), "close-drawer", "icon-btn", 'aria-label="Close Ask Valio"')}</header><div class="drawer-body">${S.request ? `<div class="request-block">${esc(S.request)}<div class="tiny">${time(S.requestAt || new Date().toISOString())}</div></div>${S.order.reading && !S.question ? understood() : ""}${S.working ? '<div class="working"><i class="spinner"></i>Working on your order…</div>' : S.question ? `<p class="muted">${esc(S.question)}</p>` : S.order.reading ? `<div class="ask-result"><p>${summary(S.order)} ${S.order.pending} things need your OK.</p><div style="margin-top:16px">${btn("Review order", "review", "primary")}</div></div>` : ""}` : `<p class="muted">Tell Valio what's changing in your kitchen. Dishes and guests are enough.</p><p class="example">“Conference lunch Tuesday, 60 guests, one vegan option”</p><p class="example">“We're closed on Thursday”</p>`}</div><form class="composer" id="ask-form"><label class="sr-only" for="ask-input">Tell Valio what's changing</label><textarea id="ask-input" rows="3" placeholder="Tell Valio what's changing…" ${S.working || S.transcribing || S.micStarting ? "disabled" : ""}>${esc(S.input)}</textarea>${S.mediaName ? `<p class="small muted" style="margin-top:8px">${esc(S.mediaName)} ${btn("Remove", "remove-file", "link")}</p>` : ""}${S.transcribing ? `<p class="small muted">Reading your recording…</p>` : ""}${S.listening ? `<p class="small amber">Listening…</p><div class="meter"><i id="audio-level" style="width:${S.level}%"></i></div>` : ""}<div class="composer-actions">${btn(icon("paperclip") + "Add menu or photo", "attach", "attach", S.working ? "disabled" : "")}<input id="photo-file" type="file" accept="image/jpeg,image/png,image/webp" hidden><div class="row" style="gap:8px">${btn(icon("mic"), "mic", `mic ${S.listening ? "listening" : ""}`, `aria-label="${S.listening ? "Stop recording" : "Start recording"}" ${S.working || S.micStarting || S.transcribing || S.busy ? "disabled" : ""}`)}${btn("Send", "send", "primary", S.working || S.listening || S.transcribing || S.micStarting ? "disabled" : "")}</div></div></form></aside>`;
}
function understood() {
  const r = S.order.reading;
  return `<div class="between"><h3>What Valio understood</h3>${btn(S.editing ? "Done" : "Edit", "edit-reading", "link")}</div>${[
    [
      "Event",
      eventName(
        r.event || S.order.wedding?.event,
        r.date || S.order.wedding?.date,
      ),
    ],
    ["Date", date(r.date || S.order.wedding?.date)],
    ["Guests", r.covers],
    [
      "Dishes",
      r.dishes
        .map((d) => S.account.recipes[d.recipe]?.name || d.recipe)
        .join(", "),
    ],
  ]
    .map(
      ([l, v]) =>
        `<div class="field"><label>${l}</label>${S.editing ? `<input aria-label="${l}" data-reading-field="${l}" value="${esc(v)}">` : `<span>${esc(v)}</span>`}</div>`,
    )
    .join("")}`;
}
function callProducts(c, o) {
  const products = c.response?.products;
  if (!Array.isArray(products)) return "";
  return products
    .map((p) => {
      const id = p.productId,
        name =
          c.product_names?.[id] ||
          o.rows.find((r) => r.product_id === id)?.name ||
          "Product " + id;
      const price = p.comparisonPrice?.value ?? p.catalogPrice?.value;
      const unit =
        p.comparisonPrice?.value !== undefined ? p.comparisonUnit : "pack";
      const available = p.scheduleLines?.[0]?.availableDate;
      return `<p>${esc(name)} → product ${esc(id)}${price !== undefined ? ", " + money(price) + "/" + esc(unit || "pack") : ""}${available ? ", available " + date(available) : ""}</p>`;
    })
    .join("");
}
function callSummary(c) {
  const count =
    c.product_count ?? c.product_ids?.length ?? c.response?.products?.length;
  const products =
    count === undefined ? "" : ` · ${count.toLocaleString("en-GB")} products`;
  const delivery = c.requested_date ? ` for ${date(c.requested_date)}` : "";
  if (c.path?.includes("products/download"))
    return `Checked Valio's catalogue${products}`;
  if (c.path?.includes("delivery-reliability"))
    return "Checked Valio's delivery history";
  if (c.path?.includes("carbon-footprint"))
    return "Checked Valio's product footprint data";
  if (c.source === "Gemini") return "Read your kitchen request";
  const reused = c.method === "CACHE";
  if (c.path?.includes("availability"))
    return `${reused ? "Used recent Valio stock checks" : "Checked stock at Valio"}${products}${delivery}`;
  if (c.path?.includes("price"))
    return `${reused ? "Used recent Valio prices" : "Checked prices at Valio"}${products}${delivery}`;
  return `Checked Valio product data${products}${delivery}`;
}
function receipt() {
  const o = S.readOrder || S.order;
  return `<aside class="drawer receipt" aria-label="How this was decided"><header class="drawer-header"><h3>How this was decided</h3>${btn(icon("x"), "close-drawer", "icon-btn", 'aria-label="Close receipt"')}</header><div class="drawer-body"><h3>Your request</h3><p>${esc(o.request || "Prepare next week’s order from our connected menu, bookings and current stock.")}</p><span class="tiny">${time(o.request_at || o.quote_at)}</span><h3>What Valio checked</h3>${o.evidence.calls.map((c) => `<div class="receipt-entry"><p>${esc(callSummary(c))}${c.at ? " · " + time(c.at) : ""}</p>${callProducts(c, o)}<p class="tiny">${c.source === "Gemini" ? "Kitchen request" : "Valio product data"}${!c.at ? " · Check time was not recorded" : ""}</p><details><summary><span style="color:var(--blue)">Details</span></summary><pre>${esc(JSON.stringify({ request: c.request || { method: c.method, path: c.path, customer: c.customer, products: c.product_ids, date: c.requested_date }, response: c.response || { status: c.status, source: c.source, product_count: c.product_count }, checked_at: c.at, original_checks: c.origin_checked_at, timing_ms: c.duration_ms }, null, 2))}</pre></details></div>`).join("")}<h3>Rules applied</h3><p>Weekly limit ${money(o.budget)} → ${o.checks.some((c) => c.id === "budget") ? "asked Sanna" : "within limit"}</p><p class="small muted">No ${esc(o.rules.allergens.join(", "))} → ${o.rows.length} products checked</p>${o.checks.map((c) => `<p class="small muted">${c.kind === "swap" ? "Ask before swap" : c.kind === "pack" ? "Larger pack" : c.kind === "budget" ? "Spend approval" : "Delivery check"} → ${c.approved ? "OK’d " + esc(c.approved_at) : "needs your OK"}</p>`).join("")}</div></aside>`;
}
function why() {
  const o = S.readOrder || S.order;
  const r = o.rows.find((r) => r.id === S.why);
  if (!r) return "";
  const a = r.allocations;
  return `<div class="popover why-popover" role="dialog" aria-label="Why this product" style="right:${S.whyPos?.right || 24}px;top:${S.whyPos?.top || 160}px"><div class="between"><h3>Why this product</h3>${btn(icon("x"), "close-why", "icon-btn", 'aria-label="Close explanation"')}</div><p>${a.map((p) => `${esc(p.dish)} · ${p.covers} guests × ${p.per_cover} g/ml = ${p.amount.toFixed(2)} ${esc(r.unit)}.`).join(" ")} In stock: ${r.stock} ${esc(r.unit)}. Ordering ${r.units} × ${r.pack} ${esc(r.unit)} packs = ${r.ordered} ${esc(r.unit)}.</p><p class="small muted" style="margin-top:12px">${esc(r.reason)}</p><p class="tiny">Price ${money(r.comparison_price || r.unit_price)}/${esc(r.comparison_unit || r.unit)} and stock from Valio, checked ${time(o.quote_at)}.</p></div>`;
}
function invoice() {
  const o = S.account.orders.find((o) => o.order_number === S.invoice);
  return `<div class="popover" role="dialog" aria-label="Invoice" style="right:24px;top:120px;width:560px"><div class="between"><h3>Invoice · ${esc(o.order_number)}</h3>${btn(icon("x"), "close-invoice", "icon-btn", 'aria-label="Close invoice"')}</div><p class="muted">Hotel Aurora · ${date(o.placed_at)}</p><p style="margin-top:16px">Total ${money(o.total)}</p><p class="tiny">Sample account invoice. Past quantities valued with Valio customer prices, checked ${date(o.price_checked_at)}.</p><div style="margin-top:16px">${table(["Product", "Quantity", "Total"], o.rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${r.units}</td><td class="money">${money(r.total)}</td></tr>`).join(""))}</div></div>`;
}
let catalogueRequest = 0;
async function loadCatalogue(q = "") {
  const request = ++catalogueRequest;
  S.catalogueQuery = q;
  S.busy = true;
  S.error = "";
  render();
  try {
    const out = await api("/catalogue?q=" + encodeURIComponent(q));
    if (request !== catalogueRequest) return;
    S.catalogue = out.products;
    S.catalogueLoaded = true;
  } catch (e) {
    S.error = e.message;
  } finally {
    S.busy = false;
    render();
  }
}
async function mutate(action, value) {
  return await task(async () => {
    S.order = await api("/drafts/" + S.order.draft_id + "/change", {
      action,
      value,
    });
  });
}
async function send() {
  if (S.working) return;
  const oldTotal = S.order.total;
  S.input = $("#ask-input")?.value || S.input;
  if (!S.input.trim() && !S.media) return;
  const text = S.question
    ? (S.questionContext || S.request) + ". " + S.input.trim()
    : S.input.trim();
  S.request = text || S.mediaName;
  S.requestAt = new Date().toISOString();
  S.input = "";
  S.working = true;
  S.question = "";
  S.steps = [{ label: stageNames[0], done: false }];
  if (S.path !== "/dashboard") {
    S.path = "/dashboard";
    history.pushState({}, "", "/dashboard");
  }
  render();
  try {
    if (S.order.status === "placed") {
      S.order = await api("/drafts", {});
      localStorage.setItem("aurora-draft", S.order.draft_id);
    }
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_id: S.order.draft_id,
        text,
        media: S.media,
        replace_event_id: S.replaceEventId,
      }),
    });
    if (!r.ok) {
      const v = await r.json();
      throw Error(v.error || "Could not update your order.");
    }
    const reader = r.body.getReader(),
      decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let end;
      while ((end = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, end);
        buf = buf.slice(end + 2);
        if (!chunk.startsWith("data: ")) continue;
        const event = JSON.parse(chunk.slice(6));
        if (event.type === "step") {
          const i = [
            "read",
            "scaled",
            "stock",
            "packs",
            "allergens",
            "budget",
          ].indexOf(event.stage);
          if (i >= 0) {
            S.steps[i] = {
              ...S.steps[i],
              label: checklistLabel(i, event),
              done: true,
              result: event.result,
              attention: event.attention,
            };
            if (i < 5)
              S.steps[i + 1] = {
                label: checklistLabel(i + 1, event),
                done: false,
              };
            render();
          }
        }
        if (event.type === "error") throw Error(event.error);
        if (event.type === "result") {
          if (event.order.question) {
            S.question = event.order.question;
            S.questionContext = event.order.reading?.transcript || S.request;
            S.input = text;
          } else {
            S.order = event.order;
            S.replaceEventId = null;
            S.filter = "changed";
          }
          S.media = null;
          S.mediaName = "";
          render();
        }
      }
    }
  } catch (e) {
    S.error = e.message;
  } finally {
    S.working = false;
    render();
    const el = $("#animated-total");
    if (el && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const start = performance.now(),
        end = S.order.total;
      function count(t) {
        const p = Math.min(1, (t - start) / 400);
        el.textContent = money(
          oldTotal + (end - oldTotal) * (1 - Math.pow(1 - p, 3)),
        );
        if (p < 1) requestAnimationFrame(count);
      }
      requestAnimationFrame(count);
    }
  }
}
let recordingSession = null,
  micGeneration = 0;
function cleanRecording(session) {
  if (!session || session.cleaned) return;
  session.cleaned = true;
  cancelAnimationFrame(session.frame);
  session.stream?.getTracks().forEach((track) => track.stop());
  if (session.context && session.context.state !== "closed")
    Promise.resolve(session.context.close()).catch(() => {});
}
async function stopMicrophone(discard = false) {
  if (S.micStarting) {
    micGeneration++;
    S.micStarting = false;
    if (recordingSession?.stream) cleanRecording(recordingSession);
    recordingSession = null;
    return;
  }
  if (S.listening) {
    if (recordingSession) recordingSession.discard = discard;
    await microphone();
  }
}
async function microphone() {
  if (S.listening) {
    const session = recordingSession;
    S.listening = false;
    S.transcribing = !session.discard;
    session.recorder.stop();
    cleanRecording(session);
    render();
    return;
  }
  if (S.micStarting || S.transcribing || S.busy || S.working) return;
  const generation = ++micGeneration,
    session = { chunks: [], cleaned: false, discard: false };
  recordingSession = session;
  S.micStarting = true;
  S.error = "";
  render();
  try {
    session.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (generation !== micGeneration) {
      cleanRecording(session);
      return;
    }
    session.context = new AudioContext();
    session.analyser = session.context.createAnalyser();
    session.analyser.fftSize = 256;
    session.context
      .createMediaStreamSource(session.stream)
      .connect(session.analyser);
    session.recorder = new MediaRecorder(session.stream);
    session.recorder.ondataavailable = (e) => {
      if (e.data.size) session.chunks.push(e.data);
    };
    session.recorder.onstop = async () => {
      cleanRecording(session);
      const current = recordingSession === session;
      if (current) {
        recordingSession = null;
        S.listening = false;
        S.micStarting = false;
        S.transcribing = !session.discard;
      }
      if (session.discard || !current) {
        if (current) render();
        return;
      }
      render();
      try {
        const blob = new Blob(session.chunks, {
          type: session.recorder.mimeType,
        });
        const data = await asBase64(blob);
        const out = await api("/transcribe", {
          media: { mime: blob.type.split(";")[0], data },
        });
        S.input = out.transcript;
      } catch (e) {
        S.error = e.message;
      } finally {
        S.transcribing = false;
        render();
      }
    };
    session.recorder.start();
    S.listening = true;
    S.micStarting = false;
    render();
    function meter() {
      if (!S.listening || recordingSession !== session) return;
      const values = new Uint8Array(session.analyser.frequencyBinCount);
      session.analyser.getByteFrequencyData(values);
      S.level = Math.min(
        100,
        (values.reduce((sum, n) => sum + n, 0) / values.length) * 2,
      );
      const el = $("#audio-level");
      if (el) el.style.width = S.level + "%";
      session.frame = requestAnimationFrame(meter);
    }
    meter();
  } catch (e) {
    if (generation !== micGeneration) {
      cleanRecording(session);
      return;
    }
    session.discard = true;
    cleanRecording(session);
    if (session.recorder?.state === "recording") session.recorder.stop();
    if (recordingSession === session) recordingSession = null;
    S.micStarting = false;
    S.listening = false;
    S.transcribing = false;
    S.error = ["NotAllowedError", "PermissionDeniedError"].includes(e.name)
      ? "Microphone access was not available. Check your browser permission or type your request."
      : "Recording could not start. Please try again, or type your request.";
    render();
  }
}

function asBase64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1]);
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}
document.addEventListener("click", async (e) => {
  const link = e.target.closest("[data-nav]");
  if (link) {
    e.preventDefault();
    navigate(link.dataset.nav);
    return;
  }
  const draft = e.target.closest("[data-open-draft]");
  if (draft) {
    e.preventDefault();
    await task(async () => {
      S.order = await api("/drafts/" + draft.dataset.openDraft);
      localStorage.setItem("aurora-draft", S.order.draft_id);
      S.readOrder = null;
      S.filter = "all";
      S.path = "/orders/week-47";
      history.pushState({}, "", S.path);
    });
    return;
  }
  const open = e.target.closest("[data-open-order]");
  if (open) {
    e.preventDefault();
    const id = open.dataset.openOrder;
    if (id === "Week 47") {
      navigate("/orders/week-47");
      return;
    }
    const order = S.account.orders.find((o) => o.order_number === id);
    if (order?.draft_id) {
      await task(async () => {
        S.readOrder = await api("/drafts/" + order.draft_id);
        S.path = "/orders/" + id;
        history.pushState({}, "", S.path);
      });
    } else if (order) {
      S.readOrder = {
        ...order,
        checks: [],
        rules: S.account.rules,
        evidence: { calls: [] },
        budget: S.account.rules.weekly_limit,
        request: "Account past order",
        quote_at: order.price_checked_at,
      };
      S.path = "/orders/" + id;
      history.pushState({}, "", S.path);
      render();
    }
    return;
  }
  const b = e.target.closest("[data-action]");
  if (!b) return;
  const action = b.dataset.action;
  const value = b.dataset.value;
  if (["company", "account-menu", "menu", "allergen"].includes(action)) {
    if (action === "company") S.companyNote = true;
    if (action === "account-menu") S.accountMenu = !S.accountMenu;
    if (action === "menu") S.menu = !S.menu;
    if (action === "allergen") S.addAllergen = true;
    render();
    return;
  }
  if (action === "login") {
    await task(async () => {
      await api("/login", {});
      S.notice = "";
      S.companyNote = false;
      S.account = await api("/account");
      await ensureDraft();
      navigate("/dashboard");
    });
    return;
  }
  if (action === "logout") {
    await stopMicrophone(true);
    await task(async () => {
      await api("/logout", {});
      S.path = "/";
      history.pushState({}, "", "/");
      S.account = null;
      S.order = null;
    });
    return;
  }
  if (action === "ask") {
    S.drawer = "ask";
    S.bell = false;
    render();
    $("#ask-input")?.focus();
    return;
  }
  if (action === "close-drawer") {
    if (S.listening || S.micStarting) await stopMicrophone();
    S.input = $("#ask-input")?.value || S.input;
    S.drawer = null;
    render();
    return;
  }
  if (action === "review") {
    S.drawer = null;
    navigate("/orders/week-47");
    return;
  }
  if (action === "receipt") {
    S.drawer = "receipt";
    render();
    return;
  }
  if (action === "bell") {
    S.bell = !S.bell;
    if (S.bell) {
      await refreshAccount();
      localStorage.setItem(
        "aurora-read",
        JSON.stringify(S.account.events.map((e) => e.id)),
      );
    }
    render();
    return;
  }
  if (action === "filter") {
    S.filter = value;
    render();
    return;
  }
  if (action === "order-tab") {
    S.tab = value;
    render();
    return;
  }
  if (action === "orders") {
    S.tab = "Placed";
    navigate("/orders");
    return;
  }
  if (action === "dashboard") {
    navigate("/dashboard");
    return;
  }
  if (action === "why") {
    S.why = value;
    const rect = b.getBoundingClientRect();
    S.whyPos = {
      right: Math.max(16, window.innerWidth - rect.right),
      top: Math.max(80, Math.min(window.innerHeight - 350, rect.bottom + 8)),
    };
    render();
    return;
  }
  if (action === "close-why") {
    S.why = null;
    render();
    return;
  }
  if (action === "invoice") {
    S.invoice = value;
    render();
    return;
  }
  if (action === "close-invoice") {
    S.invoice = null;
    render();
    return;
  }
  if (action === "qty") {
    await mutate("quantity", {
      id: b.dataset.rowId,
      units: Number(b.dataset.units),
    });
    return;
  }
  if (["approve", "unapprove", "restore"].includes(action)) {
    await mutate(action, value);
    return;
  }
  if (["small-cream", "keep-original"].includes(action)) {
    await mutate(action);
    return;
  }
  if (action === "change-order") {
    S.filter = "all";
    render();
    document
      .querySelector(".delivery-section")
      ?.scrollIntoView({ behavior: "smooth" });
    return;
  }
  if (action === "place") {
    await task(async () => {
      S.order = await api("/drafts/" + S.order.draft_id + "/place", {});
      S.drawer = null;
      navigate("/orders/confirmation");
    });
    return;
  }
  if (action === "search") {
    e.preventDefault();
    loadCatalogue($("#catalogue-search input").value);
    return;
  }
  if (action === "add") {
    S.notice = "";
    await task(async () => {
      if (S.order.status === "placed") {
        S.order = await api("/drafts", {});
        localStorage.setItem("aurora-draft", S.order.draft_id);
      }
      S.order = await api("/drafts/" + S.order.draft_id + "/change", {
        action: "add",
        value,
      });
      S.notice = "Added to next week’s order.";
    });
    return;
  }
  if (action === "copy") {
    try {
      await navigator.clipboard.writeText(S.account.mcp_url);
      S.notice = "MCP address copied.";
    } catch {
      S.notice = "Select and copy the MCP address above.";
    }
    render();
    return;
  }
  if (action === "allergen-confirm") {
    const a = $("#new-allergen").value;
    S.addAllergen = false;
    await saveRule("allergens", [...S.account.rules.allergens, a]);
    return;
  }
  if (action === "edit-reading") {
    if (S.editing) {
      const fields = Object.fromEntries(
        [...document.querySelectorAll("[data-reading-field]")].map((el) => [
          el.dataset.readingField,
          el.value,
        ]),
      );
      S.replaceEventId = S.order.reading?.event_id;
      S.input = `${fields.Event} on ${fields.Date}, ${fields.Guests} guests. ${fields.Dishes}.`;
      S.editing = false;
      render();
      $("#ask-input").value = S.input;
      await send();
    } else {
      S.editing = true;
      render();
    }
    return;
  }
  if (action === "attach") {
    $("#photo-file").click();
    return;
  }
  if (action === "remove-file") {
    S.media = null;
    S.mediaName = "";
    render();
    return;
  }
  if (action === "mic") {
    await microphone();
    return;
  }
  if (action === "send") {
    e.preventDefault();
    await send();
  }
});
document.addEventListener("submit", (e) => {
  if (e.target.id === "ask-form") {
    e.preventDefault();
    send();
  }
  if (e.target.id === "catalogue-search") {
    e.preventDefault();
    loadCatalogue(e.target.q.value);
  }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "ask-input") S.input = e.target.value;
  if (e.target.matches("#catalogue-search input"))
    S.catalogueQuery = e.target.value;
});
let ruleQueue = Promise.resolve(),
  pendingRules = {};
function saveRule(key, value) {
  pendingRules[key] = value;
  S.account.rules = { ...S.account.rules, [key]: value };
  S.rulesSaving = true;
  S.notice = "";
  ruleQueue = ruleQueue.then(async () => {
    S.rulesSaving = true;
    try {
      const saved = await api("/rules", { [key]: value });
      if (JSON.stringify(pendingRules[key]) === JSON.stringify(value))
        delete pendingRules[key];
      S.account.rules = { ...saved, ...pendingRules };
      if (!Object.keys(pendingRules).length) {
        if (S.order.status === "draft")
          S.order = await api("/drafts/" + S.order.draft_id);
        S.rulesSaving = Object.keys(pendingRules).length > 0;
        S.notice = S.rulesSaving ? "" : "Rules saved.";
      }
    } catch (e) {
      if (JSON.stringify(pendingRules[key]) === JSON.stringify(value))
        delete pendingRules[key];
      S.error = e.message;
      S.rulesSaving = Object.keys(pendingRules).length > 0;
    }
    render();
  });
  return ruleQueue;
}
document.addEventListener("change", async (e) => {
  if (e.target.id === "photo-file") {
    const f = e.target.files[0];
    if (!f) return;
    if (f.size > 6000000) {
      S.error = "Choose a photo smaller than 6 MB.";
      render();
      return;
    }
    S.media = { mime: f.type, data: await asBase64(f) };
    S.mediaName = f.name;
    render();
    return;
  }
  if (e.target.dataset.rule) {
    const key = e.target.dataset.rule;
    const value =
      e.target.type === "checkbox"
        ? e.target.checked
        : e.target.type === "number"
          ? Number(e.target.value)
          : e.target.value;
    await saveRule(key, value);
  }
});
document.addEventListener("keydown", async (e) => {
  if (e.key === "Escape") {
    if (S.listening || S.micStarting) await stopMicrophone();
    S.drawer = null;
    S.why = null;
    S.invoice = null;
    S.bell = false;
    S.menu = false;
    render();
  }
  if (
    e.key === "/" &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) &&
    S.account
  ) {
    e.preventDefault();
    S.drawer = "ask";
    render();
    $("#ask-input")?.focus();
  }
  if (
    e.key === "Enter" &&
    e.target.matches("tr[data-open-order],tr[data-open-draft]")
  )
    e.target.click();
});
window.addEventListener("popstate", () => {
  S.path = location.pathname;
  S.readOrder = null;
  render();
});
setInterval(() => {
  if (
    S.account &&
    !S.working &&
    !S.busy &&
    document.visibilityState === "visible"
  )
    refreshAccount();
}, 30000);
boot();
