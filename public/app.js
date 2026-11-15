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
const num = (n) =>
  Number(n ?? 0).toLocaleString("en-GB", { maximumFractionDigits: 2 });
const U = (u) => (u === "l" || u === "L" ? "L" : u === "pcs" ? "packs" : u || "");
const packLabel = (r) =>
  `${r.sales_unit === "KI" ? "Case of " : ""}${num(r.pack)} ${U(r.unit)}`;
let pendingChanges = 0;
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
const plural = (n, word) => `${Number(n).toLocaleString("en-GB")} ${word}${Number(n) === 1 ? "" : "s"}`;
async function api(path, body, tries = 3) {
  let r;
  for (let i = 0; ; i++) {
    try {
      r = await fetch("/api" + path, {
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      if (i < tries - 1) { await new Promise((ok) => setTimeout(ok, 1500 * (i + 1))); continue; }
      throw Error("Your connection dropped. Nothing was changed. Try again.");
    }
    // The server answers 503 + Retry-After only when Valio's own service was busy and nothing changed,
    // so repeating the same request is safe.
    if (r.status === 503 && r.headers.get("Retry-After") && i < tries - 1) {
      await new Promise((ok) => setTimeout(ok, 1000 * Number(r.headers.get("Retry-After") || 3)));
      continue;
    }
    break;
  }
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
  if (path === "/dashboard" && S.order?.status === "placed") {
    // The placed order lives in Orders. The dashboard shows what is still open.
    S.order = null;
    render();
    api("/account")
      .then((a) => {
        S.account = a;
        return ensureDraft();
      })
      .then(render)
      .catch((e) => {
        S.error = e.message;
        render();
      });
  }
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
const draftStorageKey = () =>
  "valio-draft-v3:" + (S.account?.account_id || "aurora");
async function ensureDraft() {
  const prepared = S.account?.drafts?.find(
    (d) => d.placed_by === "Sanna Virtanen",
  );
  const id = localStorage.getItem(draftStorageKey()) || prepared?.draft_id;
  if (id) {
    try {
      S.order = await api("/drafts/" + id);
      if (S.order.status !== "placed") {
        localStorage.setItem(draftStorageKey(), S.order.draft_id);
        return;
      }
      localStorage.removeItem(draftStorageKey());
    } catch {
      localStorage.removeItem(draftStorageKey());
    }
  }
  S.order = await api("/drafts", {});
  localStorage.setItem(draftStorageKey(), S.order.draft_id);
}
async function boot() {
  render();
  try {
    S.account = await api("/account");
    await ensureDraft();
    render();
    if (S.path === "/catalogue") loadCatalogue();
    if (S.path.startsWith("/orders/draft-")) {
      S.order = await api("/drafts/" + S.path.slice("/orders/draft-".length));
      localStorage.setItem(draftStorageKey(), S.order.draft_id);
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
    location.replace(
      "/?next=" + encodeURIComponent(location.pathname) + "#signin",
    );
  }
}
function table(head, rows, cls = "") {
  return `<div class="table-wrap"><table class="table ${cls}"><thead><tr>${head.map((h, i) => `<th class="${/Total|price/.test(h) ? "money" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td colspan="${head.length}" class="empty">No orders in this view.</td></tr>`}</tbody></table></div>`;
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
  const active = S.path.startsWith("/settings")
    ? "/settings/rules"
    : S.path.startsWith("/orders")
      ? "/orders"
      : S.path;
  document.body.className =
    (S.drawer ? "has-drawer " : "") +
    (S.drawer === "receipt" ? "has-receipt" : "");
  $("#app").innerHTML =
    `<aside class="sidebar ${S.menu ? "open" : ""}"><div class="brand"><div class="wordmark">Valio Aimo</div><div class="tiny">${esc(S.account?.name || "Hotel Aurora")}</div></div><nav>${nav.map(([label, path, ic]) => `<a class="nav-item ${active === path ? "current" : ""}" href="${path}" data-nav="${path}">${icon(ic, "nav-icon")}${label}</a>`).join("")}</nav>${S.accountMenu ? btn(icon("log-out") + "Sign out", "logout", "ghost") : ""}<button class="account-row" data-action="account-menu"><span class="avatar">SV</span><span>Sanna Virtanen<span class="tiny" style="display:block">Head chef</span></span></button></aside><div class="workspace"><header class="topbar"><h1>${esc(title())}</h1><span class="wordmark mobile-brand">Valio Aimo</span><div class="top-actions">${btn(icon("mic") + '<span class="ask-label">Ask Valio</span>', "ask", "secondary ask-open", 'aria-label="Ask Valio"')}${btn(icon("bell") + (unread() ? '<i class="unread"></i>' : ""), "bell", "icon-btn bell", 'aria-label="Account events"')}${btn(icon("menu"), "menu", "icon-btn mobile-menu", 'aria-label="Open menu"')}</div></header><main><h1 class="mobile-title">${esc(title())}</h1>${S.error && S.drawer !== "ask" ? `<div role="alert" class="error">${esc(S.error)}</div>` : ""}${!S.order || !S.account ? '<div class="skeleton" aria-label="Loading account"><div class="skeleton-line"></div><div class="skeleton-line"></div></div>' : page()}</main>${footer()}</div>${S.drawer ? drawer() : ""}${S.bell ? events() : ""}${S.why ? why() : ""}${S.invoice ? invoice() : ""}`;
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
  const used = (o.week_placed || 0) + o.total;
  const max = Math.max(used, o.budget) * 1.04,
    limit = (o.budget / max) * 100;
  return `<div class="budget" aria-label="${money(used)} of ${money(o.budget)} weekly limit"><i class="budget-fill" style="width:${(Math.min(used, o.budget) / max) * 100}%"></i><i class="budget-over" style="width:${(Math.max(0, used - o.budget) / max) * 100}%"></i><i class="budget-tick" style="left:${limit}%"></i></div>`;
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
  const weekday = event.date
    ? new Date(event.date + "T12:00:00").toLocaleDateString("en-GB", {
        weekday: "long",
      })
    : "delivery";
  if (event.kind === "products")
    return [
      "Reading your request",
      "Finding matching products",
      `Checking ${weekday} stock and order-by times at Valio`,
      "Comparing prices and pack sizes",
      "Checking your kitchen rules",
      "Checking your limits",
    ][i];
  if (i === 1)
    return event.covers
      ? `Scaling to ${event.covers} guests`
      : S.steps[1]?.label || "Scaling your recipes";
  if (i === 2) return `Checking ${weekday} stock at Valio`;
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
  return `<div class="delivery-mini"><span>${date(d.date)}</span><span class="muted">· arrival time to confirm · ${plural(d.rows.filter((r) => r.units > 0).length, "product")} ·</span><span>${money(d.subtotal)}</span></div>`;
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
  const count = o.rows.filter((r) => r.units > 0).length;
  const done = !count && o.week_placed > 0;
  const heading = S.working
    ? "Updating next week's order"
    : done
      ? "Week 47 is ordered"
      : pending
        ? `Next week's order needs ${pending} OK${pending > 1 ? "s" : ""}`
        : "Next week's order is ready";
  const guests = S.account.bookings.reduce((n, b) => n + b.covers, 0);
  return `<div class="subline">${stamp} · ordering for week 47</div><div class="dashboard-grid"><section class="card order-card"><div class="between"><h2>${heading}</h2><span class="pill ${S.working ? "" : done ? "ok" : pending ? "warn" : "ok"}">${S.working ? "Updating…" : done ? "Placed" : pending ? `${pending} to approve` : "Ready to send"}</span></div><p class="prepared">${done ? "Everything your menu needs is ordered or in stock. Ask Valio if plans change." : o.source === "Aurora Group assistant" ? "Prepared by Aurora Group assistant, on top of your standing week." : `Prepared from your menu, ${guests} booked guests and current stock.`}</p><p class="totals">${done ? `<span>${money(o.week_placed)} placed</span>` : `<span data-total="${o.total}">${count} product${count === 1 ? "" : "s"} · ${o.deliveries.length} deliver${o.deliveries.length === 1 ? "y" : "ies"} · <span id="animated-total">${money(o.total)}</span></span>${o.week_placed ? ` + ${money(o.week_placed)} already placed,` : ""}`} of your ${money(o.budget)} weekly limit</p>${budget(o)}${S.working ? checklist() : o.deliveries.map(deliveryMini).join("")}${o.request && !S.working ? `<p class="change-summary">${summary(o)}</p>` : ""}<div class="row order-actions">${done ? btn("View orders", "orders", "primary") : btn("Review order", "review", "primary", S.working ? "disabled" : "")}${btn(done ? "Order something more" : "Change something", "ask", "ghost")}</div></section><section class="card summary-card"><h3>This week and month</h3>${summaryRows(o)}</section></div><section class="recent"><h3>Recent orders</h3>${orderTable(S.account.orders.slice(0, 5), true)}</section>`;
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
function weekdayOf(day) {
  return day
    ? new Date(day + "T12:00:00").toLocaleDateString("en-GB", {
        weekday: "long",
      })
    : "";
}
function requestLabel(o) {
  const r = o.reading;
  if (!r) return "your kitchen change";
  if (r.kind === "products" && !r.dishes?.length) return "your product request";
  if (r.kind === "close") return `the ${weekdayOf(r.date)} closure`;
  if (r.kind === "note") return "your guests' needs";
  return `${weekdayOf(r.date)} ${esc(eventName(r.event, r.date).toLowerCase())}`;
}
function summary(o) {
  const n = o.rows.filter((r) => r.change).length;
  const delta = o.total - (o.previous_total ?? o.baseline_total);
  const amount = `${delta >= 0 ? "+" : "−"}${money(Math.abs(delta))}`;
  if (o.reading?.kind === "note")
    return "Noted. Nothing was added to the order.";
  if (o.unchanged) return "This is already in your order. Nothing changed.";
  const none = o.checks.find((c) => c.id.startsWith("line-none"));
  if (none) return esc(none.title) + ".";
  if (!n && Math.abs(delta) < 0.005)
    return "This is already in your order. Nothing changed.";
  return `${delta >= 0 ? "Added or changed" : "Removed or reduced"} ${n} product${n === 1 ? "" : "s"} for ${requestLabel(o)} (${amount}).`;
}
function summaryRows(o) {
  const cuts = o.deliveries
    .map((d) => d.cutoff)
    .filter(Boolean)
    .sort();
  const cut = cuts[0];
  const left = cut ? Math.max(0, new Date(cut) - Date.now()) : 0;
  const spent = o.month_spent ?? S.account.month_spent;
  const monthly = o.monthly_limit ?? o.rules.monthly_limit;
  return `<div class="summary-row"><span>Order by</span><span>${cut ? `${date(cut).split(" ")[0]} ${time(cut)}<br><span class="tiny">${left ? `${Math.floor(left / 3600000)} h ${Math.floor((left % 3600000) / 60000)} min left` : "Order-by time has passed"}</span>` : "To confirm"}</span></div><div class="summary-row"><span>First delivery</span><span>${date(o.deliveries[0]?.date)}<br><span class="tiny">Arrival time to confirm</span></span></div><div class="summary-row"><span>Placed for week 47</span><span>${money(o.week_placed || 0)} of ${money(o.budget)}</span></div><div class="summary-row"><span>Spent in November</span><span class="${spent > monthly ? "amber" : ""}">${money(spent)} of ${money(monthly)}</span></div><div class="summary-row"><span>Left this month</span><span>${money(Math.max(0, monthly - spent))}</span></div>`;
}
function orderNote(o) {
  if (o.status === "Draft")
    return o.placed_by === "Aurora Group assistant"
      ? "Prepared by Aurora Group assistant" +
          (o.pending ? " · needs your OK" : "")
      : "";
  if (o.historical) return "";
  if (o.rule_note) return o.rule_note;
  return "";
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
          `<tr class="clickable ${Date.now() - new Date(o.placed_at) < 3000 ? "new-order" : ""}" ${o.status === "Draft" ? `data-open-draft="${esc(o.draft_id)}"` : `data-open-order="${esc(o.order_number)}"`} tabindex="0"><td><a href="/orders/${o.status === "Draft" ? "draft-" + esc(o.draft_id) : esc(o.order_number)}" ${o.status === "Draft" ? `data-open-draft="${esc(o.draft_id)}"` : `data-open-order="${esc(o.order_number)}"`}>${esc(o.order_number)}</a></td><td><span class="placed-by">${o.placed_by === "Aurora Group assistant" ? icon("plug") : ""}${esc(o.placed_by)}</span>${!recent && orderNote(o) ? `<span class="tiny">${esc(orderNote(o))}</span>` : ""}</td><td>${recent ? (o.status === "Delivered" ? date(o.deliveries[o.deliveries.length - 1]?.date) : "Not delivered") : date(o.placed_at)}${recent ? "" : `<span class="tiny">${time(o.placed_at)}</span>`}</td><td>${recent ? o.products : o.deliveries.length}</td><td class="money">${money(o.total)}</td><td>${recent ? `<span class="small muted">${esc(o.within_rules === false ? "Approved by Sanna" : o.within_rules ? "Within your rules" : "")}</span>` : `<span class="pill ${o.status === "Delivered" ? "" : o.status === "Draft" && o.pending ? "warn" : "ok"}">${esc(o.status === "Draft" && o.pending ? "Needs OK" : o.status)}</span>`}</td></tr>`,
      )
      .join(""),
  );
}
function ordersPage() {
  // The account's draft list can lag the open draft (a fresh draft is indexed after /account loaded).
  const drafts = (S.account.drafts || []).filter(
    (d) => String(d.status).toLowerCase() === "draft",
  );
  const open = S.order;
  if (
    open?.status === "draft" &&
    open.rows.some((r) => r.units > 0) &&
    !drafts.some((d) => d.draft_id === open.draft_id)
  )
    drafts.unshift({
      ...open,
      order_number: "Week 47",
      placed_by: open.source || "Sanna Virtanen",
      placed_at: open.quote_at,
      status: "Draft",
      products: open.rows.filter((r) => r.units > 0).length,
    });
  const rows =
    S.tab === "Drafts"
      ? drafts
      : S.account.orders.filter((o) => o.status === S.tab);
  return `<div class="tabs">${["Drafts", "Placed", "Delivered"].map((t) => btn(t, "order-tab", S.tab === t ? "active" : "", `data-value="${t}"`)).join("")}</div>${orderTable(rows)}`;
}
function approvalTitle(c, o) {
  if (c.title) return esc(c.title);
  if (c.kind === "swap") {
    const r = o.rows.find((r) => c.row_ids.includes(r.id));
    return `Swap salmon for ${esc(r?.name || "the available fish")}`;
  }
  if (c.kind === "pack") {
    const r = o.rows.find((r) => c.row_ids.includes(r.id));
    return `Buy cream as ${r?.units} × ${num(r?.pack)} L packs`;
  }
  return esc(c.text);
}
const checkIcons = {
  swap: "repeat-2",
  pack: "package",
  budget: "wallet",
  assumed: "clipboard-list",
  diet: "users",
  duplicate: "copy",
};
function approval(c, o) {
  if (c.approved)
    return `<div class="approval approved" data-check="${esc(c.id)}">${icon("check")}<span class="approval-copy">${approvalTitle(c, o)}: approved by ${esc(c.approved_by || "Sanna")} · ${esc(c.approved_at)}</span>${btn("Undo", "unapprove", "link", `data-value="${esc(c.id)}"`)}</div>`;
  const body = c.title || c.kind === "swap" || c.kind === "pack";
  const other =
    c.kind === "gap"
      ? c.remove_extra
        ? btn("Remove product", "remove-extra", "secondary", `data-value="${esc(c.remove_extra)}"`)
        : btn(c.row_ids.length ? "Restore quantity" : "Change with Ask Valio", c.row_ids.length ? "restore" : "ask", "secondary", `data-value="${esc(c.row_ids[0] || "")}"`)
      : c.kind === "pack"
        ? btn("Keep 1 L packs", "small-cream", "ghost")
        : c.kind === "swap"
          ? btn("Keep original", "keep-original", "ghost")
          : c.kind === "budget"
            ? btn("Change order", "change-order", "ghost")
            : btn("Change with Ask Valio", "ask", "ghost");
  return `<div class="approval" data-check="${esc(c.id)}">${icon(checkIcons[c.kind] || "circle-alert")}<div class="approval-copy"><div class="approval-title">${approvalTitle(c, o)}</div>${body ? `<p>${esc(c.text)}</p>` : ""}${c.reopened ? '<p class="reopened">The order changed after your OK, so please check this again.</p>' : ""}</div><div class="approval-buttons">${other}${c.can_approve ? btn(c.kind === "budget" ? "Approve once" : "Approve", "approve", "primary", `data-value="${esc(c.id)}"`) : ""}</div></div>`;
}
function eventTag(o) {
  if (o.reading?.kind === "note") return "Changed in this order";
  return "For " + requestLabel(o).replace(/^the /, "");
}
function rowTag(r, o) {
  if (r.edited) return "Quantity changed by you";
  if (r.assumed) return "Assumed recipe, please check";
  if (r.requested)
    return `You asked for ${num(r.requested.quantity)} ${U(r.requested.unit)} by ${date(r.requested.date)}`;
  if (r.change === "Swapped") return r.change_reason;
  if (r.role === "extra") return "Added from the catalogue";
  return eventTag(o);
}
function orderPage(o, readonly = false) {
  const count = o.rows.filter((r) => r.units > 0).length;
  const changed = o.rows.filter((r) => r.change).length;
  const notes = (o.notes || []).length
    ? `<ul class="order-notes">${o.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`
    : "";
  return `<div class="subline"><span>${o.deliveries.length} deliver${o.deliveries.length === 1 ? "y" : "ies"} · ${plural(count, "product")} · ${readonly ? "Placed " + date(o.placed_at) + (o.placed_at && !o.historical ? " " + time(o.placed_at) + " by " + esc(o.placed_by) : "") : o.source === "Aurora Group assistant" ? "Prepared by Aurora Group assistant · not placed yet" : "Not placed yet"}</span>${btn("How this was decided", "receipt", "secondary")}</div>${readonly && o.rule_note ? `<p class="rule-note">${esc(o.rule_note)}</p>` : ""}${!readonly && o.checks.length ? `<section class="approvals"><h3>Needs your OK (${o.pending})</h3><div class="approval-box">${o.checks.map((c) => approval(c, o)).join("")}</div></section>` : ""}${!readonly ? notes : ""}${!readonly ? `<div class="filter" aria-label="Order products">${btn(`Changed (${changed})`, "filter", S.filter === "changed" ? "active" : "", 'data-value="changed"')}${btn(`All (${count})`, "filter", S.filter === "all" ? "active" : "", 'data-value="all"')}</div>` : '<div style="height:16px"></div>'}${
    o.deliveries
      .map((d) => {
        const rows = d.rows.filter(
          (r) => readonly || S.filter === "all" || r.change,
        );
        if (!rows.length) return "";
        return `<section class="delivery-section"><div class="day-header"><div><h3>${date(d.date, true)} · ${o.historical ? "delivered" : "arrival time to confirm"}</h3><p>${d.cutoff ? "Order by " + date(d.cutoff) + " " + time(d.cutoff) : o.historical ? "Order-by time was not recorded" : "Order-by time to confirm"}</p></div><span>${money(d.subtotal)}</span></div>${table(["Product", "Quantity", "Unit price", "Total", ""], rows.map((r) => `<tr data-row="${esc(r.id)}"><td class="product"><div class="product-name">${esc(r.name)}</div><span class="tiny">${packLabel(r)} · <span class="product-code">${esc(r.product_id)}</span>${r.previous_units !== null && r.previous_units !== undefined && r.previous_units !== r.units ? `<span class="was"><s>was ${r.previous_units}</s></span>` : ""}</span>${r.change && !readonly ? `<span class="tag ${r.assumed ? "tag-warn" : ""}">${esc(rowTag(r, o))}</span>` : ""}</td><td>${readonly ? r.units : `<div class="stepper">${btn("−", "qty", "", `aria-label="Less ${esc(r.name)}" data-row-id="${esc(r.id)}" data-units="${r.units - 1}" ${r.units === 0 ? "disabled" : ""}`)}<input class="qty-input" type="number" inputmode="numeric" min="0" max="9999" step="1" value="${r.units}" aria-label="Packs of ${esc(r.name)}" data-qty="${esc(r.id)}">${btn("+", "qty", "", `aria-label="More ${esc(r.name)}" data-row-id="${esc(r.id)}" data-units="${r.units + 1}"`)}</div>`}</td><td class="money unit-price">${money(r.unit_price)}</td><td class="money">${money(r.total)}</td><td>${btn("Why?", "why", "link why " + (!r.change ? "unchanged" : ""), `data-value="${esc(r.id)}"`)}</td></tr>`).join(""), "order-table")}</section>`;
      })
      .join("") ||
    (!readonly && S.filter === "changed"
      ? `<p class="muted">Nothing has changed from the prepared order. ${btn("Show all products", "filter", "link", 'data-value="all"')}</p>`
      : "")
  }`;
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
  const over = (o.week_placed || 0) + o.total - o.budget;
  return `<div class="footer-bar"><div class="footer-total">Total ${money(o.total)}${over > 0 ? `<span class="amber">${money(over)} over weekly limit</span>` : ""}</div><div class="row">${o.pending ? `<span class="small muted">${o.pending} still need${o.pending === 1 ? "s" : ""} your OK</span>` : ""}${btn(S.busy ? "Checking live prices…" : "Place order", "place", "primary", !o.can_place || S.busy || S.rulesSaving || pendingChanges ? "disabled" : "")}</div></div>`;
}
function confirmation() {
  const o = S.order;
  return `<section class="card confirmation">${icon("circle-check")}<h1>Order ${esc(o.order_number || o.confirmation?.order_number)} is recorded</h1><p class="muted">${money(o.total)} · ${esc(o.rule_note || "")}</p><div class="deliveries">${o.deliveries.map(deliveryMini).join("")}</div><p class="demo-note">This is a demo account. Valio's Junction test system has no order endpoint, so the order is stored on your account and nothing is shipped. Prices and stock were checked live with Valio at ${time(o.placed_at)}.</p><div class="row" style="margin-top:24px">${btn("View orders", "orders", "primary")}${btn("Dashboard", "dashboard", "ghost")}</div></section>`;
}
function catalogue() {
  return `<form class="search-form" id="catalogue-search"><input name="q" aria-label="Search products or codes" placeholder="Search products or codes, for example lactose-free milk" value="${esc(S.catalogueQuery)}">${btn("Search", "search", "secondary", S.busy ? "disabled" : "")}</form>${S.notice ? `<p class="status-note" role="status">${esc(S.notice)} ${btn("Review order", "review", "link")}</p>` : ""}${!S.catalogueLoaded ? '<div class="skeleton" aria-label="Loading catalogue"></div>' : table(["Product", "Pack", "Code", "Price per pack", "Per kg or L", "Delivery", ""], S.catalogue.map((p) => `<tr class="${p.allowed ? "" : "unavailable"}"><td>${esc(p.name_fi || p.name)}</td><td>${packLabel({ pack: p.pack, unit: p.pack_dim, sales_unit: p.sales_unit })}</td><td class="product-code">${esc(p.id)}</td><td class="money">${money(p.unit_price)}</td><td class="money">${p.comparison_price ? money(p.comparison_price) : "—"}</td><td>${p.allowed ? date(p.delivery) : "Not available"}<span class="tiny">${p.allowed ? "In stock" : esc(p.reason)}</span></td><td>${btn("Add to order", "add", "secondary", `data-value="${esc(p.id)}" data-delivery="${esc(p.delivery || "")}" data-name="${esc(p.name_fi || p.name)}" ${!p.allowed || S.busy ? "disabled" : ""}`)}</td></tr>`).join(""))}`;
}
function deliveries() {
  const placed = S.account.orders.filter((o) => o.status === "Placed");
  const ds = placed.flatMap((o) =>
    o.deliveries.map((d) => ({ ...d, order: o.order_number })),
  );
  const mine = S.order.deliveries.map((d) => ({
    ...d,
    order: "Week 47 draft · not placed",
  }));
  const rows = [...ds, ...mine].sort((a, b) => a.date.localeCompare(b.date));
  return table(
    ["Day", "Arrival time", "Order by", "Products", "Total", "Order"],
    rows
      .map(
        (d) =>
          `<tr><td>${date(d.date, true)}</td><td>To confirm</td><td>${d.cutoff ? date(d.cutoff) + " " + time(d.cutoff) : "Order-by time to confirm"}</td><td>${d.rows.filter((r) => r.units === undefined || r.units > 0).length}</td><td class="money">${money(d.subtotal)}</td><td>${esc(d.order)}</td></tr>`,
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
  const stamp = r.changed_at
    ? `Changed by ${esc(r.changed_by || "your team")}, ${new Date(r.changed_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}`
    : "Not changed yet";
  const row = (label, control) =>
    `<div class="rule-row"><label>${label}<span class="tiny">${stamp}</span></label>${control}</div>`;
  const euro = (label, key) =>
    row(
      label,
      `<div class="row"><span>€</span><input type="number" min="1" step=".01" aria-label="${label}" data-rule="${key}" value="${r[key] ?? ""}"></div>`,
    );
  return `<section class="rule-section"><h3>Budget</h3>${euro("Weekly limit, all orders together", "weekly_limit")}${euro("Monthly limit, all orders together", "monthly_limit")}${row("When an order goes over a limit", `<select aria-label="When an order goes over a limit" data-rule="over_limit"><option value="ask" ${r.over_limit === "ask" ? "selected" : ""}>Ask me first</option><option value="block" ${r.over_limit === "block" ? "selected" : ""}>Don't allow</option></select>`)}</section><section class="rule-section"><h3>Swaps</h3>${row("Ask me before any product swap", `<input class="toggle" type="checkbox" aria-label="Ask me before any product swap" data-rule="ask_swap" ${r.ask_swap ? "checked" : ""}>`)}${row("Only swap to products with the same or fewer allergens", `<input class="toggle" type="checkbox" aria-label="Only swap to products with the same or fewer allergens" data-rule="same_allergens" ${r.same_allergens ? "checked" : ""}>`)}</section><section class="rule-section"><h3>Allergens</h3><div class="chips">${
    r.allergens
      .filter((a) => a !== "peanuts" || !r.allergens.includes("nuts"))
      .map(
        (a) =>
          `<span class="chip">No ${esc(a)}${a === "nuts" && r.allergens.includes("peanuts") ? " or peanuts" : ""} (whole kitchen)<button class="chip-remove" data-action="allergen-remove" data-value="${esc(a)}" aria-label="Remove the no ${esc(a)} rule">${icon("x")}</button></span>`,
      )
      .join("") ||
    '<span class="small muted">No kitchen-wide allergen rule.</span>'
  }</div>${
    S.addAllergen
      ? `<select id="new-allergen" aria-label="Choose allergen">${[
          "nuts",
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
  }<p class="small muted" style="margin-top:8px">Products that contain or may contain these are never ordered. Allergen data is each product's GS1 declaration in Valio's catalogue.</p></section><section class="rule-section"><h3>Bigger changes</h3>${euro("Ask me when an order grows by more than", "growth_limit")}</section><section class="rule-section"><h3>Who can order</h3>${S.account.team.map((t) => `<div class="rule-row"><span>${esc(t.name)}<span class="tiny" style="display:block">${esc(t.role)}</span></span><span class="small muted">${esc(t.permission)}</span></div>`).join("")}</section><p class="small muted">These rules apply to every order from your account: the portal, Ask Valio and connected assistants. Every rule change is written to the account log.</p>${S.notice ? `<p class="status-note" role="status">${esc(S.notice)}</p>` : ""}`;
}
function connected() {
  const last = S.account.events.find((e) => e.by === "Aurora Group assistant");
  const token = S.account.mcp_token;
  return `<h2>Connect your own AI assistant</h2><p class="muted" style="margin-top:12px">Your company's purchasing agent, Claude or ChatGPT can order from Valio through the open Model Context Protocol (MCP). It works inside the same ordering rules as your team and can never approve on your behalf.</p><h3>Address</h3><div class="copy-row"><input readonly aria-label="MCP address" value="${esc(S.account.mcp_url)}">${btn(icon("copy") + "Copy", "copy", "secondary", 'data-copy="url"')}</div><h3>Access token for Hotel Aurora</h3><div class="copy-row"><input readonly aria-label="Access token" value="${!token ? "" : S.showToken ? esc(token) : esc(token.slice(0, 12)) + "••••••••••••"}" placeholder="No token yet">${btn(S.showToken ? "Hide" : "Show", "toggle-token", "secondary")}${btn(icon("copy") + "Copy", "copy", "secondary", 'data-copy="token"')}</div><p class="small muted" style="margin-top:8px">Send it as <code>Authorization: Bearer</code> with every call. Anyone with this token can order for Hotel Aurora within your rules. ${btn("Replace token", "regenerate-token", "link")}</p><h3>Claude or ChatGPT</h3><ol class="steps"><li>Add a custom connector (Claude: Settings → Connectors; ChatGPT: Settings → Apps, developer mode).</li><li>Paste your personal connector address: ${btn("Copy connector address", "copy", "link", 'data-copy="connector"')}. It carries your token, so keep it private.</li><li>Ask in plain words: “1,000 litres of lactose-free milk by Monday”, or dishes, guests and a day.</li></ol><h3>Your own agent</h3><p class="small muted">Seven tools, from find_products and quote_products to order_products and place_order. Each returns typed JSON with a published schema. <a href="/how-it-works">How it works</a></p><h3>Connected</h3><div class="connected-row">Aurora Group assistant<span class="tiny" style="display:block">${last ? "Last used " + date(last.at) + " " + time(last.at) : "Not used yet"}</span></div>${S.notice ? `<p class="status-note" role="status">${esc(S.notice)}</p>` : ""}`;
}
function team() {
  return `<h2>Team</h2><div style="height:20px"></div>${table(["Name", "Role", "Permission"], S.account.team.map((t) => `<tr><td>${esc(t.name)}</td><td>${esc(t.role)}</td><td>${esc(t.permission)}</td></tr>`).join(""))}`;
}
function kitchenProfile() {
  const names = S.account.ingredient_names || {},
    units = S.account.ingredient_units || {};
  return `<h2>Hotel Aurora</h2><p class="muted" style="margin-top:12px">Helsinki · Customer HC-1001</p><p class="small muted" style="margin-top:16px">Hotel Aurora is a sample kitchen account. Its menus, recipes, bookings, stock and past quantities are account records. Product names, prices, availability and order-by times come from Valio.</p><section class="card"><h3>Booked guests</h3>${S.account.bookings.map((b) => `<div class="summary-row"><span>${date(b.date)}</span><span>${b.covers != null ? plural(b.covers, "guest") : "Guests not recorded"}</span></div>`).join("")}</section><section class="card"><h3>Recipes and menu</h3>${Object.entries(
    S.account.recipes,
  )
    .map(
      ([key, r]) =>
        `<details style="margin-top:12px"><summary>${esc(r.name)}</summary>${Object.entries(
          r.ingredients,
        )
          .map(
            ([name, amount]) =>
              `<p class="small muted">${esc(names[name] || name)} · ${amount != null ? `${num(amount)} ${units[name] === "l" ? "ml" : "g"} per guest` : "amount not recorded"}</p>`,
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
        `<div class="summary-row"><span>${esc(names[name] || name.replace("_", " "))}</span><span>${n == null ? "Not recorded" : n ? num(n) + " " + U(units[name] || "kg") : "Not in stock"}</span></div>`,
    )
    .join("")}</section>`;
}
function events() {
  return `<section class="popover events" aria-label="Account log"><h3>Account log</h3>${
    S.account.events.length
      ? S.account.events
          .slice(0, 14)
          .map(
            (e) =>
              `<div class="event">${e.link ? `<a href="${esc(e.link)}">${esc(e.text)}</a>` : esc(e.text)}<p class="small muted">${e.total !== null && e.total !== undefined ? money(e.total) + (e.note ? " · " : "") : ""}${esc(e.note || "")}</p><span class="tiny">${e.at ? date(e.at) + " · " + time(e.at) : "Time not recorded"}</span></div>`,
          )
          .join("")
      : '<p class="muted" style="margin-top:12px">Orders, approvals and rule changes will appear here.</p>'
  }</section>`;
}
function offers(o) {
  // Only the products this request asked for. Earlier requests' lines stay on the order, not on this answer.
  const key = (p) => String(p.name).toLowerCase() + "|" + p.quantity;
  const asked = (o.reading?.products || []).map(key);
  const rows = o.rows.filter(
    (r) =>
      r.options && r.requested && r.units > 0 && asked.includes(key(r.requested)),
  );
  if (!rows.length) return "";
  const r = rows[0];
  return `<div class="offers"><h3>Offers compared for ${num(r.requested.quantity)} ${U(r.requested.unit)} by ${date(r.requested.date)}</h3>${r.options
    .slice(0, 5)
    .map(
      (x) =>
        `<div class="offer ${rows.some((y) => y.product_id === x.product_id) ? "chosen" : ""}"><div><span class="offer-rank ${x.rank ? "" : "muted"}">${esc(x.rank || (x.status === "ok" ? "Also fits" : "Not possible"))}</span> ${esc(x.name)}</div><div class="small muted">${money(x.price_per_unit)}/${U(x.pack_unit)} · ${num(x.packs)} × ${num(x.pack)} ${U(x.pack_unit)} = ${money(x.total)}${x.note ? " · " + esc(x.note) : ""}</div></div>`,
    )
    .join(
      "",
    )}<p class="tiny">${plural(r.compared, "matching product")} checked live at Valio.</p></div>`;
}
function drawer() {
  if (S.drawer === "receipt") return receipt();
  let body;
  if (!S.request)
    body = `<p class="muted">Tell Valio what's changing in your kitchen, or what you need. Dishes and guests are enough.</p><p class="example">“Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart.”</p><p class="example">“I need 1,000 litres of lactose-free milk by Monday.”</p><p class="example">“Conference lunch Tuesday, 60 guests, one vegan option”</p><p class="example">“We're closed on Thursday”</p>`;
  else
    body = `<div class="request-block">${esc(S.request)}<div class="tiny">${time(S.requestAt || new Date().toISOString())}</div></div>${
      S.working
        ? '<div class="working"><i class="spinner"></i>Working on your order…</div>'
        : S.error
          ? `<div class="ask-question" role="alert"><h3>That didn't go through</h3><p>${esc(S.error)}</p><p class="small muted">Your order has not changed.</p></div>`
          : S.question
            ? `<div class="ask-question"><h3>Valio needs one detail</h3><p>${esc(S.question)}</p><p class="small muted">Answer below. Your order has not changed.</p></div>`
            : S.asked && S.order.reading
              ? `${understood()}${offers(S.order)}<div class="ask-result"><p>${summary(S.order)} ${S.order.pending ? `${S.order.pending} thing${S.order.pending === 1 ? " needs" : "s need"} your OK.` : "Nothing needs your OK."}</p><div style="margin-top:16px">${btn("Review order", "review", "primary")}</div></div>`
              : ""
    }`;
  return `<aside class="drawer" role="complementary" aria-label="Ask Valio"><header class="drawer-header"><h3>Ask Valio</h3>${btn(icon("x"), "close-drawer", "icon-btn", 'aria-label="Close Ask Valio"')}</header><div class="drawer-body">${body}</div><form class="composer" id="ask-form"><label class="sr-only" for="ask-input">Tell Valio what's changing</label><textarea id="ask-input" rows="3" placeholder="Tell Valio what's changing…" ${S.working || S.transcribing || S.micStarting ? "disabled" : ""}>${esc(S.input)}</textarea>${S.mediaName ? `<p class="small muted" style="margin-top:8px">${esc(S.mediaName)} ${btn("Remove", "remove-file", "link")}</p>` : ""}${S.transcribing ? `<p class="small muted">Reading your recording…</p>` : ""}${S.listening ? `<p class="small amber">Listening…</p><div class="meter"><i id="audio-level" style="width:${S.level}%"></i></div>` : ""}<div class="composer-actions">${btn(icon("paperclip") + "Add menu or photo", "attach", "attach", S.working ? "disabled" : "")}<input id="photo-file" type="file" accept="image/jpeg,image/png,image/webp" hidden><div class="row" style="gap:8px">${btn(icon("mic"), "mic", `mic ${S.listening ? "listening" : ""}`, `aria-label="${S.listening ? "Stop recording" : "Start recording"}" ${S.working || S.micStarting || S.transcribing || S.busy ? "disabled" : ""}`)}${btn("Send", "send", "primary", S.working || S.listening || S.transcribing || S.micStarting ? "disabled" : "")}</div></div></form></aside>`;
}
function understood() {
  const r = S.order.reading;
  const menu = r.dishes?.length;
  const fields = menu
    ? [
        ["Event", eventName(r.event, r.date)],
        ["Date", date(r.date)],
        ["Guests", r.covers],
        [
          "Dishes",
          r.dishes
            .map(
              (d) =>
                (d.name || S.account.recipes[d.recipe]?.name || d.recipe) +
                (d.covers !== r.covers ? ` (${d.covers})` : ""),
            )
            .join(", "),
        ],
      ]
    : r.kind === "close"
      ? [["Closed", date(r.date)]]
      : [];
  (r.products || []).forEach((p) =>
    fields.push(
      ["Product", p.name],
      ["Amount", `${num(p.quantity)} ${U(p.unit)}`],
      ["Deliver by", date(r.date)],
    ),
  );
  (r.dietary || []).forEach((d) => fields.push(["Guests' needs", d.label]));
  const editable = menu && !(r.products || []).length;
  return `<div class="between"><h3>What Valio understood</h3>${editable ? btn(S.editing ? "Done" : "Edit", "edit-reading", "link") : ""}</div>${fields
    .map(
      ([l, v]) =>
        `<div class="field"><label>${l}</label>${S.editing && editable ? `<input aria-label="${l}" data-reading-field="${l}" value="${esc(v)}">` : `<span>${esc(v)}</span>`}</div>`,
    )
    .join(
      "",
    )}${(r.assumptions || []).length ? `<div class="assumed-list"><span class="tiny">Valio assumed</span>${r.assumptions.map((a) => `<p class="small">${esc(a)}</p>`).join("")}</div>` : ""}`;
}
function callProducts(c, o) {
  const products = c.response?.products;
  if (!Array.isArray(products) || !c.path) return "";
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
      return `<p class="small">${esc(name)} <span class="product-code">${esc(id)}</span>${price !== undefined ? " · " + money(price) + "/" + esc(U((unit || "pack").toLowerCase())) : ""}${available ? " · available " + date(available) : ""}</p>`;
    })
    .join("");
}
function callSummary(c) {
  const count =
    c.product_count ?? c.product_ids?.length ?? c.response?.products?.length;
  const products =
    count === undefined ? "" : ` · ${plural(count, "product")}`;
  const delivery = c.requested_date ? ` for ${date(c.requested_date)}` : "";
  if (c.path?.includes("products/download"))
    return `Loaded Valio's catalogue${products}`;
  if (c.path?.includes("delivery-reliability"))
    return "Loaded Valio's delivery history";
  if (c.path?.includes("carbon-footprint"))
    return "Loaded Valio's product footprint data";
  if (c.source === "Gemini")
    return c.purpose === "Product matching"
      ? "Matched catalogue products to your request"
      : "Read your request";
  if (c.path?.includes("availability"))
    return `Live stock check at Valio${products}${delivery}`;
  if (c.path?.includes("price"))
    return `Live price check at Valio${products}${delivery}`;
  return `Checked Valio product data${products}${delivery}`;
}
function receipt() {
  const o = S.readOrder || S.order;
  const calls = S.receipt?.calls;
  const stamp = (v) => (v ? `${date(typeof v === "number" ? new Date(v * 1000).toISOString() : v)} ${time(v)}` : "");
  const approvals = o.approvals
    ? o.approvals.map((a) => `<p class="small muted">${esc(a.label)} → approved by ${esc(a.by)} at ${esc(a.at)}</p>`)
    : (o.checks || []).map((c) => `<p class="small muted">${approvalTitle(c, o)} → ${c.approved ? `approved by ${esc(c.approved_by || "Sanna")} at ${esc(c.approved_at)}` : c.can_approve ? "waiting for your OK" : "blocked by a rule"}</p>`);
  return `<aside class="drawer receipt" aria-label="How this was decided"><header class="drawer-header"><h3>How this was decided</h3>${btn(icon("x"), "close-drawer", "icon-btn", 'aria-label="Close receipt"')}</header><div class="drawer-body"><h3>The request</h3><p>${esc(o.request || (o.historical ? "Weekly order from the kitchen's menu and bookings." : "Prepare next week’s order from our connected menu, bookings and current stock."))}</p><span class="tiny">${esc(o.prepared_by || o.source || "Sanna Virtanen")}${o.request_at ? " · " + stamp(o.request_at) : ""}</span><h3>What Valio checked</h3>${
    !calls
      ? S.receiptError
        ? `<p class="muted">${esc(S.receiptError)}</p>`
        : '<div class="working"><i class="spinner"></i>Loading the record…</div>'
      : calls.length
        ? calls
            .map(
              (c) =>
                `<div class="receipt-entry"><p>${esc(callSummary(c))}</p>${callProducts(c, o)}<p class="tiny">${c.at ? stamp(c.at) : "Time not recorded"}${c.duration_ms ? ` · ${c.duration_ms} ms` : ""} · ${c.source === "Gemini" ? "Gemini reads words only. It never sets a price or quantity." : "Valio Aimo API, customer HC-1001"}</p><details><summary><span style="color:var(--blue)">Details</span></summary><pre>${esc(JSON.stringify({ request: c.request || { method: c.method, path: c.path, customer: c.customer, products: c.product_ids, date: c.requested_date }, response: c.response || { status: c.status, source: c.source, product_count: c.product_count }, checked_at: c.at, timing_ms: c.duration_ms }, null, 2))}</pre></details></div>`,
            )
            .join("")
        : '<p class="muted">No checks were recorded for this order.</p>'
  }<h3>Rules applied</h3><p class="small muted">Weekly limit ${money(o.budget)}, all orders together → ${(o.week_placed || 0) + o.total > o.budget ? "over, a person had to approve" : "within limit"}</p><p class="small muted">${o.rules.allergens.length ? "No " + esc(o.rules.allergens.join(", ")) + ", including may-contain" : "No kitchen-wide allergen rule"} → ${o.rows.length} products checked against their GS1 allergen declarations</p>${approvals.join("") || '<p class="small muted">Nothing needed a person’s approval.</p>'}${o.status === "placed" ? `<h3>Placed</h3><p class="small muted">${esc(o.placed_by)} · ${stamp(o.placed_at)} · stored as a demo order, nothing ships</p>` : ""}</div></aside>`;
}
function why() {
  const o = S.readOrder || S.order;
  const r = o.rows.find((r) => r.id === S.why);
  if (!r) return "";
  const a = r.allocations || [];
  const u = U(r.unit);
  const per = r.unit === "l" ? "ml" : "g";
  const maths = a.length
    ? `<p>${a.map((p) => `${esc(p.dish)} · ${p.covers} guests × ${num(p.per_cover)} ${per} = ${num(p.amount)} ${u}.`).join(" ")} In stock or already ordered: ${num(r.stock)} ${u}. Ordering ${r.units} × ${num(r.pack)} ${u} = ${num(r.ordered)} ${u}.</p>`
    : "";
  const options = r.options
    ? `<div class="offers">${r.options
        .slice(0, 6)
        .map(
          (x) =>
            `<div class="offer ${x.product_id === r.product_id ? "chosen" : ""}"><div><span class="offer-rank ${x.rank ? "" : "muted"}">${esc(x.rank || (x.status === "ok" ? "Also fits" : "Not possible"))}</span> ${esc(x.name)}</div><div class="small muted">${money(x.price_per_unit)}/${U(x.pack_unit)} · ${money(x.total)}${x.note ? " · " + esc(x.note) : ""}</div></div>`,
        )
        .join("")}</div>`
    : "";
  return `<div class="popover why-popover" role="dialog" aria-label="Why this product" style="right:${S.whyPos?.right || 24}px;top:${S.whyPos?.top || 160}px"><div class="between"><h3>Why this product</h3>${btn(icon("x"), "close-why", "icon-btn", 'aria-label="Close explanation"')}</div>${maths}<p class="small muted" style="margin-top:12px">${esc(r.reason)}</p>${options}<p class="tiny">Price ${money(r.comparison_price || r.unit_price)}/${esc(U((r.comparison_unit || r.unit || "").toLowerCase()))} and stock from Valio, checked ${time(o.quote_at)}.</p></div>`;
}
function invoice() {
  const o = S.account.orders.find((o) => o.order_number === S.invoice);
  const vat = 13.5;
  const groups = (o.deliveries || []).map((d) => {
    const rows = (o.rows || []).filter((r) => r.delivery === d.date && r.units > 0);
    return `<h4 class="invoice-day">Delivered ${date(d.date, true)}<span>${money(d.subtotal)}</span></h4>${table(["Product", "Quantity", "Unit price", "Total"], rows.map((r) => `<tr><td>${esc(r.name)}<span class="tiny">${packLabel(r)}</span></td><td>${r.units}</td><td class="money">${money(r.unit_price)}</td><td class="money">${money(r.total)}</td></tr>`).join(""))}`;
  });
  return `<div class="popover invoice-popover" role="dialog" aria-label="Invoice"><div class="between"><h3>Invoice · ${esc(o.order_number)}</h3>${btn(icon("x"), "close-invoice", "icon-btn", 'aria-label="Close invoice"')}</div><p class="muted">Hotel Aurora · Customer HC-1001 · ordered ${date(o.placed_at)}</p>${groups.join("")}<div class="invoice-total"><div class="summary-row"><span>Total excluding VAT</span><span>${money(o.total)}</span></div><div class="summary-row"><span>VAT ${vat}% (food)</span><span>${money(o.total * vat / 100)}</span></div><div class="summary-row strong"><span>Total including VAT</span><span>${money(o.total * (1 + vat / 100))}</span></div></div><p class="tiny">Sample account invoice. Past quantities are valued with Valio customer prices checked ${date(o.price_checked_at)}.</p></div>`;
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
let changeQueue = Promise.resolve();
const queuedQty = {};
const round2 = (n) => Math.round(n * 100) / 100;
function retotal(o) {
  o.deliveries.forEach((d) => {
    d.subtotal = round2(d.rows.reduce((n, r) => n + r.total, 0));
  });
  o.total = round2(o.rows.reduce((n, r) => n + r.total, 0));
  o.pending = o.checks.filter((c) => !c.approved).length;
  o.can_place = false; // the server confirms before anything can be placed
}
function localChange(action, value) {
  const o = S.order;
  if (action === "quantity") {
    [o.rows, ...o.deliveries.map((d) => d.rows)].forEach((rows) => {
      const r = rows.find((r) => r.id === value.id);
      if (!r) return;
      r.units = value.units;
      r.total = round2(value.units * r.unit_price);
      r.ordered = round2(value.units * r.pack);
    });
    o.checks.forEach((c) => {
      if (c.approved && c.row_ids.includes(value.id)) {
        c.approved = false;
        c.reopened = true;
      }
    });
  }
  if (action === "approve" || action === "unapprove") {
    const c = o.checks.find((c) => c.id === value);
    if (c) {
      c.approved = action === "approve";
      c.reopened = false;
      c.approved_by = "Sanna";
      c.approved_at = new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Europe/Helsinki",
      });
    }
  }
  retotal(o);
}
// The screen answers at once; the server re-checks in order and has the last word.
function mutate(action, value) {
  const id = S.order.draft_id;
  S.error = "";
  if (["quantity", "approve", "unapprove"].includes(action))
    localChange(action, value);
  if (action === "quantity") {
    const waiting = value.id in queuedQty;
    queuedQty[value.id] = value.units;
    if (waiting) {
      render();
      return changeQueue;
    }
  }
  pendingChanges++;
  render();
  changeQueue = changeQueue.then(async () => {
    let body = { action, value };
    if (action === "quantity") {
      body.value = { id: value.id, units: queuedQty[value.id] };
      delete queuedQty[value.id];
    }
    try {
      const out = await api("/drafts/" + id + "/change", body);
      pendingChanges--;
      if (!pendingChanges && S.order.draft_id === id) S.order = out;
    } catch (e) {
      pendingChanges--;
      S.error = e.message;
      try {
        if (!pendingChanges) S.order = await api("/drafts/" + id);
      } catch {}
    }
    if (!["INPUT"].includes(document.activeElement?.tagName) || !pendingChanges)
      render();
  });
  return changeQueue;
}
async function send() {
  if (S.working) return;
  const oldTotal = S.order.total;
  S.input = $("#ask-input")?.value || S.input;
  if (!S.input.trim() && !S.media) return;
  // A short reply answers Valio's question. A full sentence is a new request.
  const text =
    S.question && S.input.trim().length < 60
      ? (S.questionContext || S.request) + ". " + S.input.trim()
      : S.input.trim();
  S.request = text || S.mediaName;
  S.requestAt = new Date().toISOString();
  S.input = "";
  S.working = true;
  S.question = "";
  S.error = "";
  S.asked = false;
  S.editing = false;
  S.steps = [{ label: "Reading your request", done: false }];
  if (S.path !== "/dashboard") {
    S.path = "/dashboard";
    S.readOrder = null;
    history.pushState({}, "", "/dashboard");
  }
  render();
  try {
    await changeQueue;
    if (S.order.status === "placed") {
      S.order = await api("/drafts", {});
      localStorage.setItem(draftStorageKey(), S.order.draft_id);
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
          } else {
            S.order = event.order;
            S.asked = true;
            S.replaceEventId = null;
            S.filter = event.order.rows.some((r) => r.change)
              ? "changed"
              : "all";
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
      localStorage.setItem(draftStorageKey(), S.order.draft_id);
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
  if (["account-menu", "menu", "allergen", "toggle-token"].includes(action)) {
    if (action === "toggle-token") S.showToken = !S.showToken;
    if (action === "account-menu") S.accountMenu = !S.accountMenu;
    if (action === "menu") S.menu = !S.menu;
    if (action === "allergen") S.addAllergen = true;
    render();
    return;
  }
  if (action === "logout") {
    await stopMicrophone(true);
    await task(async () => {
      await api("/logout", {});
      location.href = "/";
    });
    return;
  }
  if (action === "ask") {
    if (S.order?.status === "placed" || S.readOrder) {
      S.readOrder = null;
    }
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
    S.receipt = null;
    S.receiptError = "";
    render();
    const o = S.readOrder || S.order;
    try {
      S.receipt = o.draft_id
        ? await api("/drafts/" + o.draft_id + "/receipt")
        : { calls: [] };
    } catch (e) {
      S.receiptError = e.message;
    }
    render();
    return;
  }
  if (action === "remove-extra") {
    await mutate(action, value);
    return;
  }
  if (action === "allergen-remove") {
    await saveRule(
      "allergens",
      S.account.rules.allergens.filter(
        (a) => a !== value && !(value === "nuts" && a === "peanuts"),
      ),
    );
    return;
  }
  if (action === "regenerate-token") {
    if (
      !confirm(
        "Replace the access token? Assistants using the old token stop working until you give them the new one.",
      )
    )
      return;
    await task(async () => {
      S.account.mcp_token = (await api("/mcp-token", {})).mcp_token;
      S.showToken = true;
      S.notice = "New token created. The old one no longer works.";
    });
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
    refreshAccount();
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
    await changeQueue;
    await task(async () => {
      S.order = await api("/drafts/" + S.order.draft_id + "/place", {});
      S.account = await api("/account");
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
        localStorage.setItem(draftStorageKey(), S.order.draft_id);
      }
      const day = b.dataset.delivery;
      S.order = await api("/drafts/" + S.order.draft_id + "/change", {
        action: "add",
        value: { product_id: value, delivery: day },
      });
      const row = S.order.rows.find((r) => r.id === "extra-" + value);
      S.notice = `Added ${b.dataset.name} to the ${date(day, true)} delivery${row ? ` (${row.units} on the order, ${money(row.total)})` : ""}.`;
    });
    return;
  }
  if (action === "copy") {
    const what = b.dataset.copy || "url";
    const text =
      what === "token"
        ? S.account.mcp_token
        : what === "connector"
          ? S.account.mcp_url + "?token=" + S.account.mcp_token
          : S.account.mcp_url;
    try {
      await navigator.clipboard.writeText(text);
      S.notice =
        what === "token"
          ? "Token copied."
          : what === "connector"
            ? "Connector address copied. Keep it private."
            : "MCP address copied.";
    } catch {
      S.notice = "Copying is blocked in this browser. Show the token and copy it by hand.";
    }
    render();
    return;
  }
  if (action === "allergen-confirm") {
    const a = $("#new-allergen").value;
    S.addAllergen = false;
    await saveRule("allergens", [
      ...S.account.rules.allergens,
      a,
      ...(a === "nuts" ? ["peanuts"] : []),
    ]);
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
  if (e.target.dataset.qty) {
    const units = Math.round(Number(e.target.value));
    if (!Number.isFinite(units) || units < 0 || units > 9999) {
      S.error = "Use a whole number of packs from 0 to 9999.";
      render();
      return;
    }
    mutate("quantity", { id: e.target.dataset.qty, units });
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
  if (e.key === "Enter" && e.target.matches("[data-qty]")) e.target.blur();
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
    !pendingChanges &&
    document.visibilityState === "visible"
  )
    refreshAccount();
}, 30000);
boot();
