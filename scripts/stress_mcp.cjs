/* MCP stress part: N outside clients, each in its own test kitchen, plus bad/no-token calls.
   Run alone: node scripts/stress_mcp.cjs [BASE_URL]   (or required by stress_live.cjs) */
const { randomUUID } = require("node:crypto");

async function mcpClient(base, idx, log, isolate) {
  const run = randomUUID().replaceAll("-", "");
  const iso = isolate ? { "x-valio-test-run": run } : {};
  const rec = { client: idx, kitchen: isolate ? "test-" + run : "private demo copy", calls: [], errors: [], expected: [] };
  const t = async (name, fn) => {
    const t0 = Date.now();
    try {
      const v = await fn();
      rec.calls.push({ name, ms: Date.now() - t0, ...v });
      return v;
    } catch (e) {
      rec.calls.push({ name, ms: Date.now() - t0, status: "exception", text: String(e.message).slice(0, 300) });
      rec.errors.push({ name, kind: "exception", text: String(e.message).slice(0, 300) });
    }
  };
  // Sign in (own private copy of the demo account) of the demo account and read its MCP token (what Settings shows).
  const login = await fetch(base + "/api/login", { method: "POST", headers: { ...iso, "content-type": "application/json" }, body: "{}" });
  if (login.status >= 400) rec.errors.push({ name: "login", kind: "http", status: login.status, text: (await login.text()).slice(0, 300) });
  const cookie = (login.headers.get("set-cookie") || "").split(";")[0];
  const acct = await fetch(base + "/api/account", { headers: { ...iso, cookie } });
  // Same token Settings → Connected assistants shows for this signed-in copy.
  const token = acct.ok ? (await acct.json()).mcp_token : null;
  if (!token) { rec.errors.push({ name: "account", kind: "no-token", status: acct.status }); return rec; }
  let id = 0;
  const rpc = async (method, params, tok = token) => {
    const h = { Accept: "application/json, text/event-stream", "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25" };
    if (tok) h.Authorization = "Bearer " + tok;
    const r = await fetch(base + "/mcp/", { method: "POST", headers: h, body: JSON.stringify({ jsonrpc: "2.0", id: ++id, method, params: params || {} }) });
    const raw = await r.text();
    let body = null;
    try {
      body = (r.headers.get("content-type") || "").includes("event-stream")
        ? raw.split("\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6))).pop()
        : JSON.parse(raw);
    } catch { /* non-JSON */ }
    return { status: r.status, raw, body };
  };
  const tool = async (name, args, expectError = null) =>
    t(name, async () => {
      const r = await rpc("tools/call", { name, arguments: args });
      const res = r.body?.result || {};
      const text = (res.content || []).map((c) => c.text || "").join(" ");
      const sc = res.structuredContent || {};
      const out = { status: r.status, isError: !!res.isError, rpcError: r.body?.error || null, text: text.slice(0, 400), sc };
      if (r.status >= 400 || r.body?.error) rec.errors.push({ name, kind: "http/rpc", status: r.status, text: (r.body?.error ? JSON.stringify(r.body.error) : r.raw).slice(0, 300) });
      else if (res.isError) (expectError && expectError.test(text) ? rec.expected : rec.errors).push({ name, kind: "isError", text: text.slice(0, 300) });
      return out;
    });
  await t("initialize", async () => {
    const r = await rpc("initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "stress-" + idx, version: "1" } });
    if (r.status !== 200) rec.errors.push({ name: "initialize", kind: "http", status: r.status, text: r.raw.slice(0, 300) });
    return { status: r.status };
  });
  await t("tools/list", async () => {
    const r = await rpc("tools/list");
    const names = (r.body?.result?.tools || []).map((x) => x.name);
    if (r.status !== 200 || !names.length) rec.errors.push({ name: "tools/list", kind: "http", status: r.status, text: r.raw.slice(0, 300) });
    return { status: r.status, tools: names };
  });
  await tool("find_products", { query: "lactose-free milk" });
  const q = await tool("quote_products", { query: "lactose-free milk", quantity: 1000, unit: "l", deliver_by: "Monday" });
  const pid = q?.sc?.offers?.[0]?.product_id || "463380";
  await tool("check_stock_and_prices", { product_ids: [pid], delivery_date: "2026-11-18" });
  const o = await tool("order_products", { items: [{ query: "lactose-free milk", quantity: 1000, unit: "l" }], deliver_by: "Monday" });
  if (o) rec.milk = { status: o.sc?.status, total: o.sc?.total, message: o.sc?.message, approvals: (o.sc?.approvals || []).map((a) => a.reason) };
  const w = await tool("prepare_order", { request: "Wedding for 120 guests on Saturday: salmon soup, whitefish with potatoes, lemon tart" });
  const draft = w?.sc?.draft_id || o?.sc?.draft_id;
  if (draft) {
    const p = await tool("place_order", { draft_id: draft }, /approv|review|OK|limit|chef/i);
    rec.place = { isError: p?.isError, text: p?.text?.slice(0, 300) };
  } else rec.errors.push({ name: "place_order", kind: "no-draft", text: "prepare_order/order_products returned no draft_id" });
  await tool("place_order", { draft_id: "does-not-exist" }, /not found|no draft|unknown|find|Choose an order/i);
  log(`mcp client ${idx} done: ${rec.calls.length} calls, ${rec.errors.length} errors`);
  return rec;
}

async function authChecks(base) {
  const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", params: {} });
  const h = { Accept: "application/json, text/event-stream", "Content-Type": "application/json" };
  const out = [];
  for (const [name, tok] of [["bad token", "vat_YXVyb3Jh_" + "x".repeat(24)], ["no token", null], ["garbage token", "not-a-token"]]) {
    const r = await fetch(base + "/mcp/", { method: "POST", headers: tok ? { ...h, Authorization: "Bearer " + tok } : h, body });
    out.push({ name, status: r.status, text: (await r.text()).slice(0, 300), ok: r.status === 401 });
  }
  return out;
}

async function runMcp(base, n = 3, log = console.log, isolate = false) {
  const t0 = Date.now();
  const [clients, auth] = await Promise.all([Promise.all(Array.from({ length: n }, (_, i) => mcpClient(base, i, log, isolate).catch((e) => ({ client: i, calls: [], errors: [{ name: "client", kind: "exception", text: e.message }], expected: [] })))), authChecks(base)]);
  return { ms: Date.now() - t0, clients, auth };
}
module.exports = { runMcp };
if (require.main === module)
  runMcp(process.argv[2] || process.env.BASE_URL || "https://valio.72.61.22.106.sslip.io").then((r) => console.log(JSON.stringify(r, null, 2)));
