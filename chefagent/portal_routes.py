import base64, json, queue, threading, time
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from . import portal as p, kitchen as k
from .kitchen_intake import understand

router = APIRouter(prefix="/api")


def signed_in(req: Request):
    try:
        auth = k.unseal(req.cookies.get("aurora_account", ""))
        if auth.get("account") != "Hotel Aurora":
            raise ValueError()
    except (ValueError, k.KitchenError):
        raise k.KitchenError("Sign in to Hotel Aurora to continue.")
    origin = req.headers.get("origin")
    if (
        origin
        and origin.rstrip("/") != str(req.base_url).rstrip("/")
        and origin != "https://valio-menu-to-delivery.vercel.app"
    ):
        raise k.KitchenError("Open this order in your Valio account.")


@router.post("/login")
def login():
    r = JSONResponse({"account": "Hotel Aurora"})
    r.set_cookie(
        "aurora_account",
        k.seal({"created": time.time(), "account": "Hotel Aurora"}),
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
    return p.account()


@router.post("/rules", dependencies=[Depends(signed_in)])
async def rules(req: Request):
    return p.save_rules(await req.json())


@router.post("/drafts", dependencies=[Depends(signed_in)])
def new():
    return p.new_draft()


@router.get("/drafts/{draft_id}", dependencies=[Depends(signed_in)])
def get(draft_id: str):
    return p.get_draft(draft_id)


@router.post("/drafts/{draft_id}/change", dependencies=[Depends(signed_in)])
async def change(draft_id: str, req: Request):
    body = await req.json()
    return p.change(draft_id, body.get("action"), body.get("value"))


@router.post("/drafts/{draft_id}/place", dependencies=[Depends(signed_in)])
def place(draft_id: str):
    return p.place(draft_id)


@router.get("/catalogue", dependencies=[Depends(signed_in)])
def search(q: str = ""):
    return p.search(q)


@router.post("/transcribe", dependencies=[Depends(signed_in)])
async def transcribe(req: Request):
    body = await req.json()
    reading = understand(media=body.get("media"), source="audio")
    return {"transcript": reading["transcript"]}


@router.post("/ask", dependencies=[Depends(signed_in)])
async def ask(req: Request):
    body = await req.json()
    q = queue.Queue()

    def run():
        last = [time.monotonic()]
        reading = {}

        def progress(stage, data):
            elapsed = time.monotonic() - last[0]
            if elapsed < 0.6:
                time.sleep(0.6 - elapsed)
            last[0] = time.monotonic()
            result = None
            attention = False
            if stage == "read":
                reading.update(data)
                result = f"{len(data['dishes'])} dishes, {sum(len(p.f.RECIPES[d['recipe']]['ingredients']) for d in data['dishes'])} ingredients"
            elif stage == "scaled":
                result = "for " + __import__("datetime").date.fromisoformat(
                    reading.get("date", "2026-11-21")
                ).strftime("%A %d %b")
            elif stage == "stock":
                # These are actual shortlisted product responses, not a canned result.
                originals = [p.f.INGREDIENTS["fish"]["ids"][0]]
                late = len(
                    {
                        pid
                        for _, av in data.values()
                        for pid in originals
                        if pid in av
                        and (
                            not av[pid].get("orderable")
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
                attention = any(c["kind"] == "gap" for c in data["checks"])
            elif stage == "budget":
                result = (
                    f"€{max(0, data['total'] - data['budget']):.2f} over"
                    if data["total"] > data["budget"]
                    else "within your limit"
                )
                attention = data["total"] > data["budget"]
            q.put(
                {
                    "type": "step",
                    "stage": stage,
                    "result": result,
                    "attention": attention,
                    "covers": data.get("covers") if stage == "read" else None,
                    "date": reading.get("date"),
                }
            )

        try:
            out = p.apply_request(
                body.get("draft_id"),
                text=body.get("text"),
                media=body.get("media"),
                source="photo" if body.get("media") else "text",
                progress=progress,
            )
            q.put({"type": "result", "order": out})
        except Exception as exc:
            q.put(
                {
                    "type": "error",
                    "error": str(exc)
                    if isinstance(exc, k.KitchenError)
                    else "Valio could not finish that check. Your order has not changed. Try again.",
                }
            )
        finally:
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

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
