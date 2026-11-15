"""Catalog access and lexical search (BM25 over English + Finnish names, brand and ingredients)."""
import json, re, unicodedata, threading, fcntl
from functools import lru_cache
from pathlib import Path
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
TEMP = Path("/tmp/chefdata")
_INIT_LOCK = threading.Lock()
TOKEN = re.compile(r"[a-zåäö0-9]+")


def norm(s: str) -> str:
    return (s or "").lower()


def tokens(s: str):
    return TOKEN.findall(norm(s))


# Many suppliers leave the GS1 allergen field empty (e.g. "RB 1KG HASSELPÄHKINÄ" declares nothing).
# A product whose own name says it is an allergen is treated as containing it, whatever the field says.
NAME_ALLERGENS = {
    "nuts": re.compile(r"manteli|hasselp|cashew|pistaasi|pekaani|saksanpähk|parapähk|macadamia|makadamia|marsipaani|praliini|"
                       r"nougat|almond|hazelnut|walnut|pecan|pistachio|marzipan|praline|brazil nut|\btree ?nut"),
    "peanuts": re.compile(r"maapähk|suolapähk|peanut"),
    "sesame": re.compile(r"seesam|sesam|tahini|tahna"),
}
NOT_ALLERGEN = re.compile(r"muskottipähk|nutmeg|kookos|coconut")
# Products in these categories with no allergen declaration at all need a person to check the label
# when the kitchen bans allergens: nuts and seeds, spreads, chocolate, pastry, syrups.
RISKY_UNDECLARED = ("21460", "21453", "52201", "41763", "41764", "22140", "21992", "21150")


def enrich(p):
    text = (p["name"] + " " + p["name_fi"]).lower()
    declared = bool(p["contains"] or p["may_contain"])
    named = set() if NOT_ALLERGEN.search(text) and not re.search(r"manteli|hassel|cashew|maapähk|almond|hazel|peanut", text) else \
        {a for a, rx in NAME_ALLERGENS.items() if rx.search(text)}
    if "sesame" in named and "tahna" in text and not re.search(r"seesam|sesam|tahini", text):
        named.discard("sesame")  # "tahna" is any paste; only sesame paste counts
    if named - set(p["contains"]):
        p["contains"] = sorted(set(p["contains"]) | named)
        p["contains_from_name"] = sorted(named)
    p["undeclared"] = not declared and not named and p.get("category", "") in RISKY_UNDECLARED
    return p


class Catalog:
    def __init__(self, path=ROOT / "data" / "catalog.json"):
        self.items = [enrich(p) for p in json.loads(Path(path).read_text())]
        self.by_id = {p["id"]: p for p in self.items}
        self.food = [p for p in self.items if p["food"]]
        docs = []
        for p in self.food:
            name_toks = tokens(p["name"]) + tokens(p["name_fi"])
            # names weigh more than ingredient lists
            docs.append(name_toks * 3 + tokens(p["brand"]) + tokens(p["ingredients"])[:30])
        self.bm25 = BM25Okapi(docs)

    def get(self, pid):
        return self.by_id.get(str(pid))

    def search(self, query: str, k=20, filt=None):
        q = tokens(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            p = self.food[i]
            if filt and not filt(p):
                continue
            out.append((p, float(scores[i])))
            if len(out) >= k:
                break
        return out


def load() -> Catalog:
    # functools.lru_cache alone allows simultaneous first calls to execute the
    # wrapped function. Hold this lock around the cache lookup as well as build.
    with _INIT_LOCK:
        return _load()


@lru_cache(maxsize=1)
def _load() -> Catalog:
    """Local: data/catalog.json. On Vercel (no raw data in the repo, by Valio's data terms) the
    catalogue is built on cold start from Valio's own download API into /tmp."""
    p = ROOT / "data" / "catalog.json"
    if not p.exists():
        import os
        from . import build_catalog
        TEMP.mkdir(parents=True, exist_ok=True)
        p = TEMP / "catalog.json"
        # Multiple worker processes can share /tmp in one runtime instance.
        with (TEMP / "catalog.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not p.exists():
                build_catalog.download_raw(TEMP / "raw")
                build_catalog.main(TEMP / "raw", p)
    return Catalog(p)


def matches(p, rule) -> bool:
    """Gold-label predicate: rule = {any:[..], all:[..], none:[..]} over lower-cased en+fi name."""
    text = " " + norm(p["name"]) + " | " + norm(p["name_fi"]) + " "
    if rule.get("any") and not any(w in text for w in rule["any"]):
        return False
    if rule.get("all") and not all(w in text for w in rule["all"]):
        return False
    if any(w in text for w in rule.get("none", [])):
        return False
    return True
