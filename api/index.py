"""HTTP entry point (Vercel Python runtime or `uvicorn api.index:app`).

  GET  /                      kitchen web app (public/index.html)
  GET  /api/kitchens          demo kitchen profiles + sample menus
  POST /api/parse-menu        free-text menu -> structured services (LLM)
  POST /api/plan              menu -> draft order (deliveries, gaps, approvals, audit)
  POST /api/submit            place one delivery (mandate re-checked on Valio's side)
  POST /api/quote, /api/search, /api/substitutes
  /mcp                        MCP server (streamable HTTP, stateless) for outside agents
"""
import json, os, sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from chefagent import service, llm
from chefagent.mcp_server import mcp

mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Valio Aimo menu-to-delivery agent", lifespan=lifespan)
app.mount("/mcp", mcp_app)

SAMPLES = json.loads((ROOT / "public" / "samples.json").read_text()) if (ROOT / "public" / "samples.json").exists() else []

PARSE_PROMPT = """A hotel kitchen sent a purchasing request: a menu for next week, a direct product request
(e.g. "1,000 litres of lactose-free milk by Monday"), or both. Convert it to JSON.
Today is Saturday 2026-11-14; "Monday" means 2026-11-16, etc. If no covers are given for a line,
use the nearest covers mentioned for that meal, else 100.
Text:
---
{text}
---
Return {{"services": [{{"date": "YYYY-MM-DD", "meal": short label,
  "items": [ either a dish: {{"text": the menu line as written, "covers": int, "diet": subset of ["vegan","vegetarian","gluten-free","milk-free"]}}
             or a direct product request: {{"text": the request as written, "direct": true, "ingredient": what to buy incl. requirements (e.g. "lactose-free milk"),
               "search": [3-5 English+Finnish catalogue search phrases], "qty": number, "unit": "kg"|"l", "covers": 1, "diet": []}} ]}}]}}
For a direct request, "date" is the date the goods must arrive (e.g. "by Monday" = 2026-11-16) and meal is "Delivery"."""


@app.get("/api/kitchens")
def kitchens():
    return {"kitchens": service.KITCHENS, "samples": SAMPLES}


@app.post("/api/parse-menu")
async def parse_menu(req: Request):
    body = await req.json()
    out = llm.ask_json(PARSE_PROMPT.format(text=body.get("text", "")[:4000]))
    return out


@app.post("/api/plan")
async def plan(req: Request):
    body = await req.json()
    services = body["services"]
    if sum(len(s.get("items", [])) for s in services) > 12:
        return JSONResponse({"error": "Demo limit: at most 12 menu lines per run."}, status_code=400)
    return service.plan_menu_order(services, body.get("customer", "HC-1001"))


@app.post("/api/submit")
async def submit(req: Request):
    body = await req.json()
    return service.submit_order(body["delivery"], body.get("customer", "HC-1001"), body.get("approved_by"))


@app.post("/api/search")
async def search(req: Request):
    b = await req.json()
    return service.search_products(b["query"], b.get("diet"), b.get("customer", "HC-1001"), b.get("limit", 10))


@app.post("/api/quote")
async def quote(req: Request):
    b = await req.json()
    return service.quote(b["product_ids"], b["delivery_date"], b.get("customer", "HC-1001"))


@app.post("/api/substitutes")
async def substitutes(req: Request):
    b = await req.json()
    return service.find_substitutes(b["product_id"], b["delivery_date"], b.get("diet"), b.get("customer", "HC-1001"))


@app.get("/api/eval")
def eval_results():
    p = ROOT / "public" / "eval.json"
    return json.loads(p.read_text()) if p.exists() else {}


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")


app.mount("/", StaticFiles(directory=ROOT / "public"), name="static")
