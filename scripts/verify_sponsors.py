"""Real provider checks in an isolated test kitchen. Never prints credentials.

Use --database, --photo <path> and --audio <path>. Provider errors are reported
without response bodies, URLs or credentials. This is provider acceptance, not
a substitute for the deployed browser order flow.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chefagent.account_scope import kitchen_scope
from chefagent.account_store import Store, Conflict, clone_account
from chefagent.sponsor_media import upload_menu, transcribe, confirmation_audio


def database_probe(identity):
    store = Store("accounts/" + identity)
    if not store.aiven:
        raise RuntimeError("Aiven is not configured")
    store.put("ledger", {"orders": [], "events": [], "drafts": []})
    version = store.put("rules", {"weekly_limit": 100})
    barrier = threading.Barrier(2)
    def writer(value):
        current = Store("accounts/" + identity)
        barrier.wait()
        try:
            current.put("rules", {"weekly_limit": value}, version)
            return "committed"
        except Conflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(writer, [200, 300]))
    assert sorted(results) == ["committed", "conflict"]
    assert Store("accounts/" + identity).get("rules")[1] == "2"
    store.put("mcp", {"token": "nonfunctional-test-marker"})
    target = "accounts/test-" + uuid.uuid4().hex
    assert clone_account("accounts/" + identity, target)
    assert Store(target).get("mcp") == (None, None)
    assert Store(target).get("rules")[0] == store.get("rules")[0]
    Store(target).put("rules", {"weekly_limit": 400}, "1")
    assert store.get("rules")[0] != Store(target).get("rules")[0]
    return {"provider": "Aiven PostgreSQL", "concurrent_winners": 1, "conflicts": 1,
            "separate_connection_read": True, "private_clone_isolated": True, "cloned_token": False}


def photo_probe(path):
    import httpx
    from PIL import Image
    ext = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[ext]
    result = upload_menu({"mime": mime, "data": base64.b64encode(path.read_bytes()).decode()})
    response = httpx.get(result["preview_url"], timeout=30)
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        dimensions = image.size
    assert max(dimensions) <= 960
    assert result["type"] == "authenticated"
    return {"provider": "Cloudinary", "upload": True, "authenticated": True,
            "original_dimensions": [result["width"], result["height"]], "preview_dimensions": dimensions,
            "thumbnail_loaded": True}


def speech_probe(path):
    result = transcribe({"mime": "audio/wav", "data": base64.b64encode(path.read_bytes()).decode()})
    assert result["provider"] == "ElevenLabs"
    assert "wedding" in result["transcript"].lower() and "saturday" in result["transcript"].lower()
    audio = confirmation_audio({"status": "placed", "order_number": "TEST-ONLY", "total": 42.5})
    assert len(audio) > 1000
    return {"provider": "ElevenLabs", "transcript_checked": True,
            "confirmation_audio_bytes": len(audio), "order_action": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", action="store_true")
    parser.add_argument("--photo", type=Path)
    parser.add_argument("--audio", type=Path)
    args = parser.parse_args()
    identity = "test-" + uuid.uuid4().hex
    results = []
    with kitchen_scope(identity):
        for name, fn in [("database", lambda: database_probe(identity)), ("photo", lambda: photo_probe(args.photo)), ("audio", lambda: speech_probe(args.audio))]:
            if not getattr(args, name):
                continue
            start = time.monotonic()
            try:
                result = fn()
            except Exception as exc:
                print(json.dumps({"check": name, "pass": False, "error_class": type(exc).__name__}))
                raise SystemExit(1) from None
            results.append({"check": name, "pass": True, "duration_seconds": round(time.monotonic() - start, 3), **result})
    print(json.dumps({"scope": "isolated provider acceptance", "results": results}, indent=2))
