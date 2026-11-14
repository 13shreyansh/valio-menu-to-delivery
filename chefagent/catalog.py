"""Catalog access and lexical search (BM25 over English + Finnish names, brand and ingredients)."""
import json, re, unicodedata
from functools import lru_cache
from pathlib import Path
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"[a-zåäö0-9]+")


def norm(s: str) -> str:
    return (s or "").lower()


def tokens(s: str):
    return TOKEN.findall(norm(s))


class Catalog:
    def __init__(self, path=ROOT / "data" / "catalog.json"):
        self.items = json.loads(Path(path).read_text())
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


@lru_cache(maxsize=1)
def load() -> Catalog:
    """Local: data/catalog.json. On Vercel (no raw data in the repo, by Valio's data terms) the
    catalogue is built on cold start from Valio's own download API into /tmp."""
    p = ROOT / "data" / "catalog.json"
    if not p.exists():
        import os
        from . import build_catalog
        tmp = Path("/tmp/chefdata")
        p = tmp / "catalog.json"
        if not p.exists():
            build_catalog.download_raw(tmp / "raw")
            build_catalog.main(tmp / "raw", p)
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
