"""Client for Valio Aimo's Junction 2026 mock backend (price + availability), with
an on-disk cache (the API is rate limited and the brief asks us to query only
shortlisted products) and an optional `Disruptions` overlay used by the eval harness
to simulate stock-outs and late deliveries on top of the real responses."""
import hashlib, json, os, random, threading, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("VALIO_API_BASE", "https://junction26.valioaimo.fi")
KEY = os.environ.get("VALIO_API_KEY", "")
CACHE = ROOT / "data" / "cache" / "valio_api.json"
if os.environ.get("VERCEL"):  # read-only bundle; price/stock are always re-fetched live there
    CACHE = Path("/tmp/chefcache/valio_api.json")
_lock = threading.Lock()


class ValioBusy(Exception):
    """Valio's price or availability service kept refusing (rate limit or outage)."""
    message = ("Valio's price and stock service is busy right now, so nothing was changed. "
               "Try again in a few seconds.")
    def __str__(self): return self.message


FRESH_WINDOW = 20      # seconds: a "live" check may reuse an answer Valio gave this recently
STALE_OK = 30 * 60     # seconds: if Valio refuses every retry, reuse an answer up to this old
MIN_GAP = 0.25         # seconds between calls to Valio from this server, across all users
_gate = threading.Lock()
_mem = {}
_mem_path = [None]


def _shared_cache():
    """One in-memory cache for every request in this process, so concurrent kitchens share
    Valio's answers instead of overwriting each other's cache file."""
    with _lock:
        if _mem_path[0] != CACHE:
            _mem.clear(); _mem_path[0] = CACHE
            if CACHE.exists():
                try: _mem.update(json.loads(CACHE.read_text()))
                except ValueError: pass
        return _mem
_last_call = [0.0]


def _send(path, customer, date, chunk, attempts=6):
    """One call to Valio, serialised across threads and spaced out, with backoff on 429/5xx/timeouts.
    Returns (response, parsed body) or raises ValioBusy. Never parses a non-JSON body."""
    for attempt in range(attempts):
        with _gate:
            wait = _last_call[0] + MIN_GAP - time.time()
            if wait > 0: time.sleep(wait)
            try:
                r = httpx.post(BASE + path, headers={"X-API-Key": KEY},
                               json={"customer": customer, "requestedDate": date, "products": chunk}, timeout=12)
            except httpx.HTTPError:
                r = None
            finally:
                _last_call[0] = time.time()
        if r is not None and r.status_code == 200:
            try:
                body = r.json()
                if isinstance(body.get("products"), list): return r, body
            except ValueError:
                pass
        elif r is not None and 400 <= r.status_code < 500 and r.status_code != 429:
            r.raise_for_status()
        if attempt < attempts - 1:
            retry_after = r.headers.get("retry-after") if r is not None else None
            delay = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else min(1.0 * 2 ** attempt, 6)
            time.sleep(min(delay, 8) + random.random() * 0.5)
    raise ValioBusy()


class Disruptions:
    """Deterministic overlay: block `share` of the products in `product_ids`."""
    def __init__(self, rules=None):
        self.stockout, self.late = set(), set()
        for r in rules or []:
            for pid in r["product_ids"]:
                h = int(hashlib.sha1(f"{r['type']}:{pid}".encode()).hexdigest(), 16) % 1000 / 1000
                if h < r["share"]:
                    (self.stockout if r["type"] == "stockout" else self.late).add(pid)

    def apply(self, pid, avail):
        if pid in self.stockout:
            return {**avail, "salesBlock": True, "scheduleLines": [], "_disrupted": "stockout"}
        if pid in self.late and avail.get("scheduleLines"):
            sl = dict(avail["scheduleLines"][0]); sl["availableDate"] = "2026-12-01"
            return {**avail, "scheduleLines": [sl], "_disrupted": "late"}
        return avail


def _future_or_none(ts):
    """Preserve the supplier's cut-off, including passed ones. Callers must stop late orders."""
    return ts


class ValioAPI:
    def __init__(self, customer="HC-1001", disruptions: Disruptions | None = None, offline=False, fresh=False):
        self.customer = customer
        self.disruptions = disruptions or Disruptions()
        self.offline = offline
        self.fresh = fresh
        self.audit = []
        self.calls = 0
        self.queried = {}  # path -> set of product ids looked up (cached or live)
        self._cache = _shared_cache()

    def _save(self):
        with _lock:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(f".{threading.get_ident()}.tmp"); tmp.write_text(json.dumps(dict(self._cache))); tmp.replace(CACHE)

    def _post(self, path, date, ids):
        ids = sorted(set(ids))
        self.queried.setdefault(path, set()).update(ids)
        out, missing = {}, []
        for pid in ids:
            k = f"{self.customer}|{path}|{date}|{pid}"
            entry = self._cache.get(k)
            age = time.time() - entry.get('at', 0) if entry else None
            if entry and (self.offline or age < (FRESH_WINDOW if self.fresh else 120)):
                out[pid] = entry['row']
            else:
                missing.append(pid)
        if missing and not self.offline:
            stale = []
            for i in range(0, len(missing), 200):
                chunk = missing[i:i + 200]
                started = time.time()
                try:
                    r, body = _send(path, self.customer, date, chunk)
                except ValioBusy:
                    # Valio refused every retry. Reuse its last answer for each product if it is recent
                    # enough, and say so in the log; otherwise stop with a message the chef can act on.
                    old = {pid: self._cache.get(f"{self.customer}|{path}|{date}|{pid}") for pid in chunk}
                    if all(e and time.time() - e.get('at', 0) < STALE_OK for e in old.values()):
                        stale += chunk
                        for pid, e in old.items(): out[pid] = e['row']
                        continue
                    raise
                self.calls += 1
                self.audit.append({'method': 'POST', 'path': path, 'customer': self.customer,
                                   'requested_date': date, 'product_ids': chunk,
                                   'status': r.status_code, 'at': time.time(), 'source': 'Valio API',
                                   'duration_ms':round((time.time()-started)*1000),
                                   'request':{'customer':self.customer,'requestedDate':date,'products':chunk},'response':body})
                for row in body["products"]:
                    out[row["productId"]] = row
                    self._cache[f"{self.customer}|{path}|{date}|{row['productId']}"] = {'at': time.time(), 'row': row}
            self._save()
            missing = [pid for pid in missing if pid not in stale]
            if stale:
                origins = {pid: self._cache[f"{self.customer}|{path}|{date}|{pid}"].get('at') for pid in stale}
                self.audit.append({'method': 'CACHE', 'path': path, 'customer': self.customer, 'requested_date': date,
                                   'product_ids': stale, 'at': time.time(),
                                   'source': f"Valio was busy; reused its answer from {round((time.time()-min(origins.values()))/60)} min ago",
                                   'request': {'customer': self.customer, 'requestedDate': date, 'products': stale},
                                   'response': {'products': [out[pid] for pid in stale]}, 'origin_checked_at': origins})
        cached=[pid for pid in ids if pid not in missing]
        if cached:
            origins={pid:self._cache[f"{self.customer}|{path}|{date}|{pid}"].get('at') for pid in cached}
            self.audit.append({'id':'cache-'+hashlib.sha256(json.dumps([self.customer,path,date,origins],sort_keys=True).encode()).hexdigest(),
                               'method':'CACHE','path':path,'customer':self.customer,'requested_date':date,'product_ids':cached,
                               'at':time.time(),'source':'Valio API response, reused within 120 seconds',
                               'request':{'customer':self.customer,'requestedDate':date,'products':cached},
                               'response':{'products':[out[pid] for pid in cached]},'origin_checked_at':origins})
        return out

    def price(self, date, ids):
        """-> {pid: {unit_price, unit_price_vat, comparison_price, comparison_unit, list_price, net_price, error}}"""
        res = {}
        for pid, row in self._post("/api/price", date, ids).items():
            if row.get("error") or not row.get("catalogPrice"):
                res[pid] = {"error": True}; continue
            cp = row.get("comparisonPrice") or {}
            res[pid] = {"unit_price": row["catalogPrice"]["value"], "unit_price_vat": row["catalogPrice"].get("valueWithTax"),
                        "comparison_price": cp.get("value"), "comparison_unit": row.get("comparisonUnit"),
                        "list_price": (row.get("listPrice") or {}).get("value"), "net_price": row.get("netPriceFound", False),
                        "vat_rate": (row.get("tax") or {}).get("taxRate"), "error": False}
        return res

    def availability(self, date, ids):
        """-> {pid: {orderable, available_date, amount, unit, model, closing_time, disrupted}}"""
        res = {}
        for pid, row in self._post("/api/availability", date, ids).items():
            row = self.disruptions.apply(pid, row)
            sl = (row.get("scheduleLines") or [None])[0]
            orderable = bool(sl) and not row.get("salesBlock") and not sl.get("salesBlock") and sl.get("availableAmount", 0) > 0
            res[pid] = {"orderable": orderable, "available_date": sl.get("availableDate") if sl else None,
                        "amount": sl.get("availableAmount") if sl else 0, "unit": sl.get("salesUnit") if sl else None,
                        "model": row.get("logisticModel"), "closing_time": _future_or_none(row.get("closingTime")),
                        "stock_known": row.get("logisticModel") == "Stock", "disrupted": row.get("_disrupted")}
        return res
