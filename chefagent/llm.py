"""Minimal Gemini client (REST) with JSON output and an on-disk response cache so eval
runs are reproducible and cheap to re-score."""
import hashlib, json, os, threading, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache" / "llm"          # bundled, read-only on Vercel
WRITE_DIR = Path("/tmp/chefcache/llm") if os.environ.get("VERCEL") else CACHE_DIR
MODEL = os.environ.get("CHEF_MODEL", "gemini-3.5-flash")
_lock = threading.Lock()
STATS = {"calls": 0, "cached": 0, "tokens_in": 0, "tokens_out": 0}


READ_CACHE = True   # set False for pass^k reliability trials (fresh LLM samples each run)


def ask_json(prompt: str, system: str = "", model: str | None = None, thinking: str = "low", schema: dict | None = None, use_cache=True):
    model = model or MODEL
    key = hashlib.sha256(json.dumps([model, system, prompt, thinking, schema], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    wpath = WRITE_DIR / f"{key}.json"
    for pth in (path, wpath):
        if use_cache and READ_CACHE and pth.exists():
            STATS["cached"] += 1
            return json.loads(pth.read_text())
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2,
                                  "thinkingConfig": {"thinkingLevel": thinking}}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        body["generationConfig"]["responseJsonSchema"] = schema
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    last = None
    for attempt in range(5):
        try:
            r = httpx.post(url, headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=120)
            if r.status_code in (429, 500, 503):
                last = r.text; time.sleep(3 * (attempt + 1)); continue
            r.raise_for_status()
            d = r.json()
            text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
            out = json.loads(text)
            u = d.get("usageMetadata", {})
            with _lock:
                STATS["calls"] += 1
                STATS["tokens_in"] += u.get("promptTokenCount", 0)
                STATS["tokens_out"] += u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
            WRITE_DIR.mkdir(parents=True, exist_ok=True)
            wpath.write_text(json.dumps(out, ensure_ascii=False))
            return out
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
            last = repr(e); time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini failed: {last}")
