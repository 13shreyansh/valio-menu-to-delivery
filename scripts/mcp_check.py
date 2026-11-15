"""Outside-agent check of the MCP door. On a deployed site it uses an isolated test kitchen."""
import httpx, json, os, sys, time, uuid
B=os.environ.get("BASE_URL","http://localhost:8765")
RUN={} if "localhost" in B else {"x-valio-test-run":uuid.uuid4().hex}
c=httpx.Client(base_url=B,timeout=240,headers=RUN)
r=c.post("/api/login",json={}); c.headers["Cookie"]="aurora_account="+r.cookies.get("aurora_account"); c.cookies.clear()
acct=c.get("/api/account").json(); tok=acct["mcp_token"]
H={"Accept":"application/json, text/event-stream","Content-Type":"application/json"}
def rpc(method,params=None,token=tok):
    h=dict(H); 
    if token: h["Authorization"]="Bearer "+token
    r=httpx.post(B+"/mcp/",json={"jsonrpc":"2.0","id":1,"method":method,"params":params or {}},headers=h,timeout=240)
    return r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)
print("no token:",rpc("tools/list",token=None)[0], "bad token:",rpc("tools/list",token="vat_YXVyb3Jh_"+"x"*24)[0])
s,t=rpc("tools/list"); tools=t["result"]["tools"]; print(s,[(x["name"],bool(x.get("outputSchema"))) for x in tools])
def call(name,args):
    t0=time.time(); s,v=rpc("tools/call",{"name":name,"arguments":args}); res=v.get("result",v)
    print(f"\n{name} {round(time.time()-t0,1)}s isError={res.get('isError')} structured={bool(res.get('structuredContent'))}")
    return res.get("structuredContent") or res
q=call("quote_products",{"query":"lactose-free milk","quantity":1000,"unit":"l","deliver_by":"Monday"})
for o in q.get("offers",[])[:5]: print("  ",o.get("rank"),o["status"],o["name"][:45],o["price_per_unit"],o["total"],o.get("note"))
o=call("order_products",{"items":[{"query":"lactose-free milk","quantity":1000,"unit":"l"}],"deliver_by":"Monday"})
print("  ",o.get("status"),o.get("total"),o.get("message"),[a["reason"] for a in o.get("approvals",[])],o.get("review_url"))
o2=call("order_products",{"items":[{"query":"lactose-free milk","quantity":40,"unit":"l"}],"deliver_by":"Wednesday"})
print("  ",o2.get("status"),o2.get("total"),o2.get("message"),o2.get("order_number"))
w=call("prepare_order",{"request":"Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart."})
print("  ",w.get("status"),w.get("total"),[a["reason"] for a in w.get("approvals",[])])
for d in w.get("deliveries",[]): print("   ",d["date"],[(l["name"][:25],l["quantity"]) for l in d["products"]])
p=call("place_order",{"draft_id":w.get("draft_id")}); print("  ",json.dumps(p)[:400])
# portal same request
d=c.post("/api/drafts",json={}).json()
import re
r=c.post("/api/ask",json={"draft_id":d["draft_id"],"text":"Wedding on Saturday, 120 guests. Salmon soup, whitefish with potatoes, lemon tart."})
res=[json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")][-1]["order"]
print("\nportal wedding: total",res["total"],"delta",round(res["total"]-res["previous_total"],2),[ (c2.get("title") or c2["kind"]) for c2 in res["checks"]])
print("  changed rows:",[(x["name"][:25],x["units"],x.get("previous_units")) for x in res["rows"] if x.get("change")])
