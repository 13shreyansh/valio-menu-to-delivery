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
from chefagent.intake import parse_request
from chefagent.mcp_server import mcp

mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield

app = FastAPI(title="Valio Aimo menu-to-delivery agent", lifespan=lifespan)
app.mount("/mcp", mcp_app)
from chefagent.kitchen_routes import router as sheet_router
from chefagent.kitchen import KitchenError
app.include_router(sheet_router)

@app.exception_handler(KitchenError)
async def sheet_error(req, exc):
    return JSONResponse({"error": str(exc)}, status_code=422)


SAMPLES = json.loads((ROOT / "public" / "samples.json").read_text()) if (ROOT / "public" / "samples.json").exists() else []




@app.get("/api/kitchens")
def kitchens():
    return {"kitchens": service.KITCHENS, "samples": SAMPLES}


@app.post("/api/parse-menu")
async def parse_menu(req: Request):
    body = await req.json()
    return parse_request(body.get("text", ""))


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


@app.api_route("/api/request", methods=["GET", "POST"])
async def request_order(req: Request, text: str = "", customer: str = "HC-1001"):
    """One call, plain language in, draft order out (same as the MCP tool request_order).
    GET /api/request?text=I+need+1000+litres+of+lactose-free+milk+by+Monday&customer=HC-1001"""
    if req.method == "POST":
        b = await req.json()
        text, customer = b.get("text", ""), b.get("customer", customer)
    parsed = parse_request(text)
    services = parsed.get("services", [])
    if sum(len(s.get("items", [])) for s in services) > 12:
        return JSONResponse({"error": "Demo limit: at most 12 lines per request."}, status_code=400)
    order = service.plan_menu_order(services, customer)
    order["parsed_request"] = parsed
    return order


@app.get("/api/health")
def health(deep: int = 0):
    """Liveness. deep=1 also loads the catalogue and prices one product through Valio's API."""
    out = {"build_commit": os.environ.get("VERCEL_GIT_COMMIT_SHA"), "ok": True, "valio_key": bool(os.environ.get("VALIO_API_KEY")), "llm_key": bool(os.environ.get("GEMINI_API_KEY"))}
    if deep:
        from chefagent.catalog import load
        cat = load()
        out["catalogue_food_items"] = len(cat.food)
        q = service.quote([cat.food[0]["id"]], "2026-11-16")
        out["sample_quote_ok"] = bool(q)
    return out


@app.get("/api/eval")
def eval_results():
    p = ROOT / "public" / "eval.json"
    return json.loads(p.read_text()) if p.exists() else {}


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")


if (ROOT / "public").is_dir():  # on Vercel, public/ is served by the CDN
    app.mount("/", StaticFiles(directory=ROOT / "public"), name="static")
