"""Build a compact, searchable catalog from Valio Aimo's static product file.

Input : data/raw/products.json (+ reliability.csv, carbon.csv) from the Junction 2026 portal.
Output: data/catalog.json  - one record per product with the fields the agent needs.

Pack size (kg or L per sales unit) is estimated statically here from the name and
GS1 unit conversions. At order time the agent prefers the authoritative figure
derived from the price API (catalogPrice / comparisonPrice).
"""
import csv, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DOWNLOAD_AUDIT = []

# GS1 allergen type codes -> EU-14 allergen groups (plus a few useful sub-codes)
GS1_ALLERGEN = {
    "AC": "crustaceans", "AE": "egg", "AF": "fish", "AM": "milk", "ML": "milk",  # lactose counts as milk
    "AN": "nuts", "SA": "nuts", "SC": "nuts", "SH": "nuts", "SM": "nuts", "SP": "nuts", "SR": "nuts",
    "ST": "nuts", "SW": "nuts", "NW": "nuts",
    "AP": "peanuts", "AS": "sesame", "AU": "sulphites", "AW": "gluten", "UW": "gluten",
    "GB": "gluten", "GO": "gluten", "NR": "gluten", "GS": "gluten", "GK": "gluten",
    "AY": "soy", "BC": "celery", "BM": "mustard", "NL": "lupin", "UM": "molluscs",
}
LACTOSE_CODES = {"ML"}

SIZE_RE = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|gr|g|l|dl|cl|ml)\b", re.I)
MULTI_RE = re.compile(r"(?<![\d.,])(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|gr|g|l|dl|cl|ml)\b", re.I)
UNIT_TO = {"kg": ("kg", 1.0), "g": ("kg", 0.001), "gr": ("kg", 0.001), "l": ("l", 1.0), "dl": ("l", 0.1), "cl": ("l", 0.01), "ml": ("l", 0.001)}


def name_of(p, lang):
    for n in p.get("synkkaData", {}).get("names", []) or []:
        if n.get("language") == lang:
            return n["value"].strip()
    return ""


def text_of(arr, lang="en"):
    for n in arr or []:
        if n.get("language") == lang:
            return n["value"]
    return ""


def unit_factor(p, unit_id):
    for u in p.get("units") or []:
        if u.get("unitId") == unit_id:
            return float(u.get("sizeInBaseUnits") or 1.0)
    return None


def estimate_pack(p, name):
    """Return (amount, 'kg'|'l', method) per sales unit, or (None, None, reason)."""
    su, bu = p.get("salesUnit"), p.get("baseUnit")
    if su == "KG":
        return 1.0, "kg", "unit_kg"
    sales_factor = unit_factor(p, su) or 1.0
    base_factor = unit_factor(p, bu) or 1.0
    per_sales_in_base = sales_factor / base_factor if base_factor else sales_factor
    m = MULTI_RE.search(name)
    if m:
        n, size, unit = int(m.group(1)), float(m.group(2).replace(",", ".")), m.group(3).lower()
        dim, mult = UNIT_TO[unit]
        total = n * size * mult
        # name already describes the multipack; if the sales unit is a case of such multipacks, multiply further
        if per_sales_in_base > 1 and abs(per_sales_in_base - n) > 1e-6:
            total *= per_sales_in_base
        return round(total, 4), dim, "name_multi"
    sizes = SIZE_RE.findall(name)
    if sizes:
        # "850/500g" style: first number is gross, take the last size token (drained weight) conservatively
        size, unit = sizes[-1]
        dim, mult = UNIT_TO[unit.lower()]
        return round(float(size.replace(",", ".")) * mult * per_sales_in_base, 4), dim, "name_single"
    convs = p.get("synkkaData", {}).get("unitConversions") or []
    by_type = {c.get("synkkaPackagingType"): c for c in convs}
    base = by_type.get("BASE_UNIT_OR_EACH")
    if base and base.get("netWeight", {}).get("unit") == "GRM":
        return round(base["netWeight"]["value"] / 1000.0 * per_sales_in_base, 4), "kg", "gs1_base"
    case = by_type.get("CASE")
    if case and su != bu and case.get("netWeight", {}).get("unit") == "GRM":
        return round(case["netWeight"]["value"] / 1000.0, 4), "kg", "gs1_case"
    return None, None, "unknown"


def classif(p, name):
    for c in p.get("synkkaData", {}).get("classifications", []) or []:
        if c.get("name") == name:
            return c.get("values") or []
    return []


def download_raw(raw_dir: Path):
    """Fetch the three data files from Valio's Junction API (needs VALIO_API_KEY)."""
    import os, httpx
    raw_dir.mkdir(parents=True, exist_ok=True)
    base = os.environ.get("VALIO_API_BASE", "https://junction26.valioaimo.fi")
    h = {"X-API-Key": os.environ["VALIO_API_KEY"]}
    for path, name in [("/api/products/download", "products.json"),
                       ("/api/delivery-reliability/download", "reliability.csv"),
                       ("/api/carbon-footprint/download", "carbon.csv")]:
        with httpx.stream("GET", base + path, headers=h, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(raw_dir / name, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
            DOWNLOAD_AUDIT.append({"method":"GET","path":path,"status":r.status_code,"source":"Valio catalogue download"})


def main(raw: Path = RAW, out: Path = ROOT / "data" / "catalog.json"):
    products = json.loads((raw / "products.json").read_text())
    rel = {r["productId"]: float(r["deliveryReliability"]) for r in csv.DictReader(open(raw / "reliability.csv"))}
    co2 = {r["productId"]: float(r["AVG kg CO2-eq/kg"]) for r in csv.DictReader(open(raw / "carbon.csv"))}
    subs = {}
    for p in products:
        for s in p.get("substitutions") or []:
            subs.setdefault(s["product"], []).append(s["substituteProduct"])
    rows = []
    for p in products:
        sd = p.get("synkkaData", {}) or {}
        en, fi = name_of(p, "en"), name_of(p, "fi")
        name = en or fi
        amount, dim, method = estimate_pack(p, name)
        contains, may = set(), set()
        lactose = False
        for v in classif(p, "allergen"):
            grp = GS1_ALLERGEN.get(v["id"])
            if v["id"] in LACTOSE_CODES and v.get("unit") == "CONTAINS":
                lactose = True
            if not grp:
                continue
            if v.get("unit") == "CONTAINS":
                contains.add(grp)
            elif v.get("unit") == "MAY_CONTAIN":
                may.add(grp)
        claims = sorted({v["id"] for v in classif(p, "nutritionalClaim")})
        labels = sorted({v["id"] for v in classif(p, "packagingMarkedLabel")} - {"warmTemperature", "coolTemperature", "freezeTemperature"})
        temp = "frozen" if any(v["id"] == "freezeTemperature" for v in classif(p, "packagingMarkedLabel")) else (
            "chilled" if any(v["id"] == "coolTemperature" for v in classif(p, "packagingMarkedLabel")) else "ambient")
        vat = (sd.get("vatCode") or "").split(" ")[0]
        is_food = vat in ("MEDIUM", "LOW") or bool(classif(p, "nutritionFact"))
        ingredients_en = text_of(sd.get("keyIngredients"), "en")
        rows.append({
            "id": p["id"], "name": name, "name_fi": fi, "brand": sd.get("brand", ""),
            "vendor": p.get("vendorName", ""), "category": p.get("category", ""),
            "sales_unit": p.get("salesUnit"), "lot": p.get("allowedLotSize") or 1,
            "pack": amount, "pack_dim": dim, "pack_method": method,
            "contains": sorted(contains), "may_contain": sorted(may - contains), "lactose": lactose,
            "lactose_free": "FREE_FROM_LACTOSE" in claims, "gluten_free": "FREE_FROM_GLUTEN" in claims,
            "vegan": "VEGAN" in claims, "vegetarian": "VEGETARIAN" in claims or "VEGAN" in claims,
            "claims": claims, "labels": labels, "temp": temp, "food": is_food,
            "origin": p.get("countryOfOrigin", ""),
            "reliability": rel.get(p["id"]), "co2_per_kg": co2.get(p["id"]),
            "substitutes": subs.get(p["id"], []),
            "ingredients": ingredients_en[:400],
        })
    out_path = out
    out = [o for o in rows if o["food"] or o["id"] in {s for v in subs.values() for s in v}]
    out_path.write_text(json.dumps(out, ensure_ascii=False))
    food = [o for o in out if o["food"]]
    print(f"{len(rows)} products, {len(food)} food; pack known for "
          f"{sum(1 for o in food if o['pack'])}/{len(food)} food items", file=sys.stderr)


if __name__ == "__main__":
    main()
