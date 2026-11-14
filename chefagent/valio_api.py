"""Client for Valio Aimo's Junction 2026 mock backend (price + availability), with
an on-disk cache (the API is rate limited and the brief asks us to query only
shortlisted products) and an optional `Disruptions` overlay used by the eval harness
to simulate stock-outs and late deliveries on top of the real responses."""
import hashlib, json, os, threading, time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("VALIO_API_BASE", "https://junction26.valioaimo.fi")
KEY = os.environ.get("VALIO_API_KEY", "")
CACHE = ROOT / "data" / "cache" / "valio_api.json"
if os.environ.get("VERCEL"):  # read-only bundle; price/stock are always re-fetched live there
    CACHE = Path("/tmp/chefcache/valio_api.json")
_lock = threading.Lock()


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


class ValioAPI:
    def __init__(self, customer="HC-1001", disruptions: Disruptions | None = None, offline=False):
        self.customer = customer
        self.disruptions = disruptions or Disruptions()
        self.offline = offline
        self.calls = 0
        self._cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    def _save(self):
        with _lock:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            tmp = CACHE.with_suffix(".tmp"); tmp.write_text(json.dumps(self._cache)); tmp.replace(CACHE)

    def _post(self, path, date, ids):
        ids = sorted(set(ids))
        out, missing = {}, []
        for pid in ids:
            k = f"{path}|{date}|{pid}"
            if k in self._cache:
                out[pid] = self._cache[k]
            else:
                missing.append(pid)
        if missing and not self.offline:
            for i in range(0, len(missing), 200):
                chunk = missing[i:i + 200]
                for attempt in range(4):
                    try:
                        r = httpx.post(BASE + path, headers={"X-API-Key": KEY},
                                       json={"customer": self.customer, "requestedDate": date, "products": chunk}, timeout=30)
                        if r.status_code == 429:
                            time.sleep(2 * (attempt + 1)); continue
                        r.raise_for_status(); break
                    except httpx.HTTPError:
                        if attempt == 3: raise
                        time.sleep(2 * (attempt + 1))
                self.calls += 1
                for row in r.json()["products"]:
                    out[row["productId"]] = row
                    self._cache[f"{path}|{date}|{row['productId']}"] = row
            self._save()
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
                        "model": row.get("logisticModel"), "closing_time": row.get("closingTime"),
                        "stock_known": row.get("logisticModel") == "Stock", "disrupted": row.get("_disrupted")}
        return res
