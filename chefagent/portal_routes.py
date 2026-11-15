import base64, json, queue, threading, time, uuid
from contextvars import copy_context
from .account_scope import account_id,account_name
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse, Response
from . import portal as p, kitchen as k
from .kitchen_intake import understand
from .valio_api import ValioBusy
from .account_store import clone_account, SEED

router = APIRouter(prefix="/api")
_locks, _locks_guard = {}, threading.Lock()


def _draft_lock(account, draft_id):
    with _locks_guard:
        return _locks.setdefault((account, str(draft_id)), threading.Lock())


def signed_in(req: Request):
    try:
        auth = k.unseal(req.cookies.get("aurora_account", ""))
        if auth.get("account_id","aurora")!=account_id():
            raise ValueError()
    except (ValueError, k.KitchenError):
        raise k.KitchenError("Sign in to Hotel Aurora to continue.")
    origin = req.headers.get("origin")
    if (
        origin
        and origin.rstrip("/") != str(req.base_url).rstrip("/")
        and origin.rstrip("/") != p.SITE
    ):
        raise k.KitchenError("Open this order in your Valio account.")


@router.post("/login")
def login():
    acct = account_id()
    if acct == "aurora":
        # A private, fresh copy of Hotel Aurora for this visitor: nobody sees anyone else's orders.
        private = "demo-" + uuid.uuid4().hex
        if clone_account(SEED, "accounts/" + private) or clone_account("accounts/aurora-v3", "accounts/" + private):
            acct = private
    r = JSONResponse({"account": account_name()})
    r.set_cookie(
        "aurora_account",
        k.seal({"created": time.time(), "account": account_name(),"account_id":acct}),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=14400,
    )
    return r


@router.post("/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("aurora_account")
    return r


@router.get("/account", dependencies=[Depends(signed_in)])
def account():
    from .sponsor_media import capabilities
    return {**p.account(), "capabilities": capabilities()}


@router.post("/rules", dependencies=[Depends(signed_in)])
async def rules(req: Request):
    return p.save_rules(await req.json())


@router.post("/mcp-token", dependencies=[Depends(signed_in)])
def new_token():
    return {"mcp_token": p.mcp_token(regenerate=True)}


@router.get("/warm")
def warm():
    # Public and harmless: loads the catalogue so the first signed-in screen is quick.
    from .catalog import load
    return {"ok": True, "products": len(load().items)}


@router.post("/drafts", dependencies=[Depends(signed_in)])
def new():
    return p.slim(p.new_draft())


@router.get("/drafts/{draft_id}", dependencies=[Depends(signed_in)])
def get(draft_id: str):
    return p.slim(p.get_draft(draft_id))


@router.get("/drafts/{draft_id}/receipt", dependencies=[Depends(signed_in)])
def receipt(draft_id: str):
    return p.receipt(draft_id)


@router.post("/drafts/{draft_id}/change", dependencies=[Depends(signed_in)])
async def change(draft_id: str, req: Request):
    body = await req.json()
    return p.slim(p.change(draft_id, body.get("action"), body.get("value")))


@router.post("/drafts/{draft_id}/place", dependencies=[Depends(signed_in)])
def place(draft_id: str):
    return p.slim(p.place(draft_id))


@router.get("/catalogue", dependencies=[Depends(signed_in)])
def search(q: str = ""):
    return p.search(q)


@router.post("/transcribe", dependencies=[Depends(signed_in)])
async def transcribe(req: Request):
    from .sponsor_media import transcribe as read_recording
    body = await req.json()
    return read_recording(body.get("media"))


@router.post("/media/menu", dependencies=[Depends(signed_in)])
async def menu_photo(req: Request):
    from .sponsor_media import upload_menu
    body = await req.json()
    return upload_menu(body.get("media"))


@router.post("/drafts/{draft_id}/spoken-confirmation", dependencies=[Depends(signed_in)])
def spoken_confirmation(draft_id: str):
    from .sponsor_media import confirmation_audio
    audio = confirmation_audio(p.get_draft(draft_id))
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/ask", dependencies=[Depends(signed_in)])
async def ask(req: Request):
    body = await req.json()
    q = queue.Queue()

    def run():
        last = [time.monotonic()]
        reading = {}

        def progress(stage, data):
            elapsed = time.monotonic() - last[0]
            if elapsed < 0.35:
                time.sleep(0.35 - elapsed)
            last[0] = time.monotonic()
            result = None
            attention = False
            if stage == "read":
                reading.update(data)
                n = sum(len(d.get("ingredients") or p.f.RECIPES.get(d.get("recipe"), {}).get("ingredients", [])) for d in data.get("dishes", []))
                parts = []
                if data.get("dishes"):
                    parts.append(f"{len(data['dishes'])} dish{'es' if len(data['dishes']) != 1 else ''}, {n} ingredients")
                if data.get("products"):
                    parts.append(f"{len(data['products'])} product request{'s' if len(data['products']) != 1 else ''}")
                result = ", ".join(parts) or {"close": "kitchen closed", "note": "guest needs noted"}.get(data.get("kind"), "read")
            elif stage == "scaled":
                result = "for " + __import__("datetime").date.fromisoformat(
                    reading.get("date") or "2026-11-16"
                ).strftime("%A %d %b")
            elif stage == "stock":
                # These are actual shortlisted product responses, not a canned result.
                late = len(
                    {
                        pid
                        for day, (_, av) in data["quotes"].items()
                        for pid in data["needed"].get(day, [])
                        if pid in av
                        and (
                            not av[pid].get("orderable")
                            or (av[pid].get("available_date") or "9999") > day
                            or k.cutoff_passed(av[pid].get("closing_time"))
                        )
                    }
                )
                result = f"{late} item late" if late else "stock checked"
                attention = late > 0
            elif stage == "packs":
                count = sum(c["kind"] == "pack" for c in data["checks"])
                result = f"{count} cheaper pack" if count else "pack sizes checked"
                attention = count > 0
            elif stage == "allergens":
                result = f"{len(data['rows'])} products checked"
                attention = any(c["kind"] in ("gap", "allergen", "diet") for c in data["checks"])
                if any(c["kind"] in ("allergen", "diet") for c in data["checks"]):
                    result = "needs your attention"
            elif stage == "budget":
                over = next((c for c in data["checks"] if c["kind"] == "budget" and not c["approved"]), None)
                attention = bool(over)
                result = (over.get("title") or "needs your OK") if over else "within your limits"
            q.put(
                {
                    "type": "step",
                    "stage": stage,
                    "result": result,
                    "attention": attention,
                    "covers": data.get("covers") if stage == "read" else None,
                    "kind": reading.get("kind"),
                    "date": reading.get("date"),
                }
            )

        # One request per draft at a time: a resend after a reload waits for the first one
        # instead of colliding with it, then sees its result ("already in your order").
        lock = _draft_lock(account_id(), body.get("draft_id"))
        if not lock.acquire(timeout=90):
            q.put({"type": "error", "error": "Valio is still working on your previous request for this order. It will appear in a moment."})
            q.put(None)
            return
        try:
            out = p.apply_request(
                body.get("draft_id"),
                text=body.get("text"),
                media=body.get("media"),
                source="photo" if body.get("media") else "text",
                progress=progress,
                replace_event_id=body.get("replace_event_id"),
            )
            q.put({"type": "result", "order": p.slim(out)})
        except Exception as exc:
            q.put(
                {
                    "type": "error",
                    "error": str(exc)
                    if isinstance(exc, (k.KitchenError, ValioBusy))
                    else "Valio could not finish that check. Your order has not changed. Try again.",
                }
            )
        finally:
            lock.release()
            q.put(None)

    context=copy_context()
    threading.Thread(target=lambda:context.run(run), daemon=True).start()

    def stream():
        yield "data: " + json.dumps({"type": "start"}) + "\n\n"
        while True:
            try:
                item = q.get(timeout=10)
            except queue.Empty:
                yield ": checking\n\n"
                continue
            if item is None:
                break
            yield "data: " + json.dumps(item) + "\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
