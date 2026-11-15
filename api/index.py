"""Valio portal and a stateless Streamable HTTP MCP server."""

import os, sys
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings
from chefagent.mcp_server import mcp
from chefagent.portal_routes import router
from chefagent.kitchen import KitchenError
from chefagent.account_scope import KitchenScopeMiddleware

mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@asynccontextmanager
async def lifespan(app):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Valio Aimo", lifespan=lifespan)
app.add_middleware(KitchenScopeMiddleware)
app.mount("/mcp", mcp_app)
app.include_router(router)
# Retain signed photograph validation for existing data-layer clients.
from chefagent.kitchen_routes import photo_apply

app.add_api_route("/api/sheet/photo/apply", photo_apply, methods=["POST"])


@app.exception_handler(KitchenError)
async def error(req, exc):
    return JSONResponse({"error": str(exc)}, status_code=422)


@app.exception_handler(Exception)
async def unavailable(req, exc):
    return JSONResponse(
        {
            "error": "Valio is unavailable. Your order has not changed. Please try again."
        },
        status_code=503,
    )


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "build_commit": os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("BUILD_COMMIT"),
        "storage": bool(os.environ.get("STORE_URL") or os.environ.get("BLOB_READ_WRITE_TOKEN") or not os.environ.get("VERCEL")),
        "valio": bool(os.environ.get("VALIO_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
    }


@app.get("/samples")
def samples():
    return FileResponse(ROOT / "public" / "samples.html")


def page(name):
    from fastapi.responses import HTMLResponse
    from chefagent.portal import SITE

    html = (ROOT / "public" / name).read_text().replace("https://valio-menu-to-delivery.vercel.app", SITE)
    return HTMLResponse(html, headers={"Cache-Control": "public, max-age=0, s-maxage=300, stale-while-revalidate=86400"})


@app.get("/")
def landing():
    return page("landing.html")


@app.get("/how-it-works")
def how():
    return page("how.html")


@app.get("/dashboard")
@app.get("/orders")
@app.get("/orders/{order_id}")
@app.get("/catalogue")
@app.get("/deliveries")
@app.get("/invoices")
@app.get("/settings/{section}")
@app.get("/settings")
def portal(order_id: str = "", section: str = ""):
    return FileResponse(
        ROOT / "public" / "index.html", headers={"Cache-Control": "no-cache"}
    )


app.mount("/", StaticFiles(directory=ROOT / "public"), name="static")
