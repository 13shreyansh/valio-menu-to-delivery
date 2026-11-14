"""Deterministic scorer for a planned order against the gold recipe cards.

Independent of the agent's code paths: it re-derives allergen/diet violations from the raw
catalogue fields with its own rules, re-checks availability through the same API cache +
disruption overlay the agent saw, and matches products to gold ingredients by the gold rules.
"""
import math, statistics

from eval.gold.dishes import BY_ID
from eval.gold.ingredients import I

COVER_OK = 0.8        # >= 80% of the gold quantity counts as enough to cook
QTY_BAND = 0.30       # "accurate" quantity = within +-30% of gold


def gold_match(p, iid):
    r = I[iid]
    if p["category"] not in r["cats"]:
        return False
    t = (" " + p["name"] + " | " + p["name_fi"] + " ").lower()
    if r["any"] and not any(w in t for w in r["any"]):
        return False
    return not any(w in t for w in r["none"])


def independent_violations(p, diet, policy):
    """Spec-level check written separately from chefagent/guardrails.py."""
    out = []
    c, m = set(p["contains"]), set(p["may_contain"])
    for a in policy.get("free_from", []):
        if a in c or (policy.get("strict_may_contain") and a in m):
            out.append(f"{a}")
    if "gluten-free" in diet and ("gluten" in c or ("gluten" in m and not p.get("gluten_free"))):
        out.append("gluten")
    cat = p["category"]
    meat = cat[:3] in ("187", "188", "172") or cat[:4] in ("4170", "4171", "4172") or cat in ("21510", "21530")
    if "vegan" in diet:
        dairy_like = cat.startswith("10") and cat not in ("10402", "10406", "10413", "10418", "10641", "10530", "10531", "10532", "10517", "10515", "10516", "10518")
        if c & {"milk", "egg", "fish", "crustaceans", "molluscs"} or ((meat or dairy_like) and not p.get("vegan")) or cat == "22150":
            out.append("not vegan")
    if "vegetarian" in diet and (meat or c & {"fish", "crustaceans", "molluscs"}):
        out.append("not vegetarian")
    if policy.get("lactose_free_dairy") and "milk" in c and not p.get("lactose_free"):
        if cat in ("10400", "10401", "10405", "10411", "10412", "10419", "10430", "10432", "10404") or p.get("lactose"):
            out.append("lactose")
    return out


def score_case(case, order, catalog, api):
    policy = case["kitchen"]["policy"]
    items = [it for s in case["services"] for it in s["items"]]
    dates = [s["date"] for s in case["services"] for _ in s["items"]]
    lines = [l for d in order["deliveries"] for l in d["lines"]]
    # independent availability re-check
    by_date = {}
    for l in lines:
        by_date.setdefault(l["delivery_date"], []).append(l["product_id"])
    avail = {}
    for d, ids in by_date.items():
        for pid, a in api.availability(d, ids).items():
            avail[(d, pid)] = a
    per_item = [[] for _ in items]
    line_ok = {}
    for li, l in enumerate(lines):
        p = catalog.get(l["product_id"])
        a = avail.get((l["delivery_date"], l["product_id"]), {})
        deliverable = bool(a.get("orderable")) and (not a.get("available_date") or a["available_date"] <= l["delivery_date"])
        pack_ok = l["ordered_kg"] >= 0.97 * sum(x["kg"] for x in l["allocations"])
        line_ok[li] = deliverable and pack_ok
        for al in l["allocations"]:
            per_item[al["item"]].append((li, l, p, al["kg"]))
    res_items, violations = [], []
    for ix, it in enumerate(items):
        dish = BY_ID[it["dish"]]
        service_date = dates[ix]
        diet = it.get("diet", [])
        # allergen / diet violations on anything allocated to this dish
        for li, l, p, kg in per_item[ix]:
            v = independent_violations(p, diet, policy)
            if v:
                violations.append({"case": case["id"], "item": it["text"], "product": p["name"], "violates": v})
        comps = []
        for c in dish["components"]:
            best = None
            for iid, g in list(c["accept"].items()) + [(k, v) for k, v in c.get("subs", {}).items()]:
                is_sub = iid in c.get("subs", {})
                got = [(li, l, kg) for li, l, p, kg in per_item[ix] if gold_match(p, iid)]
                if is_sub:
                    got = [x for x in got if x[1].get("needs_approval")]
                kg = sum(x[2] for x in got)
                ok_lines = all(line_ok[x[0]] and x[1]["delivery_date"] <= service_date for x in got)
                exp = g * it["covers"] / 1000.0
                cand = {"ingredient": iid, "kg": round(kg, 3), "expected": round(exp, 3), "sub": is_sub,
                        "ratio": round(kg / exp, 3) if exp else None, "deliverable": ok_lines and bool(got)}
                if got and (best is None or cand["kg"] / max(cand["expected"], 1e-9) > best["kg"] / max(best["expected"], 1e-9)):
                    best = cand
            covered = bool(best) and best["deliverable"] and best["ratio"] >= COVER_OK
            comps.append({"accept": list(c["accept"]), "ess": c["ess"], "best": best, "covered": covered})
        ess = [c for c in comps if c["ess"]]
        item_viol = [v for v in violations if v["item"] == it["text"]]
        cookable = all(c["covered"] for c in ess) and not item_viol
        res_items.append({"text": it["text"], "dish": it["dish"], "covers": it["covers"], "cookable": cookable,
                          "ess_covered": sum(c["covered"] for c in ess), "ess_total": len(ess),
                          "missing": [c["accept"][0] for c in ess if not c["covered"]], "components": comps,
                          "violations": item_viol})
    # lines that no gold component asked for (waste/noise)
    used = set()
    for ix, it in enumerate(items):
        dish = BY_ID[it["dish"]]
        ids = {i for c in dish["components"] for i in list(c["accept"]) + list(c.get("subs", {}))}
        for li, l, p, kg in per_item[ix]:
            if any(gold_match(p, i) for i in ids):
                used.add(li)
    extra = [lines[i] for i in range(len(lines)) if i not in used]
    ratios = [c["best"]["ratio"] for r in res_items for c in r["components"] if c["ess"] and c["best"] and c["best"]["ratio"]]
    return {"case": case["id"], "items": res_items, "violations": violations,
            "cookable": sum(r["cookable"] for r in res_items), "dishes": len(res_items),
            "ess_covered": sum(r["ess_covered"] for r in res_items), "ess_total": sum(r["ess_total"] for r in res_items),
            "qty_ratios": ratios, "extra_lines": len(extra), "extra_eur": round(sum(l["line_total"] for l in extra), 2),
            "lines": len(lines), "total_eur": order["total"], "gaps": len(order["gaps"]),
            "subs_flagged": sum(1 for l in lines if l.get("substitution") and l.get("needs_approval")),
            "subs_auto": sum(1 for l in lines if l.get("substitution") and not l.get("needs_approval")),
            "recipe_subs_unflagged": sum(1 for l in lines if (l.get("substitution") or {}).get("type") == "recipe" and not l.get("needs_approval"))}


def summarize(scores):
    D = sum(s["dishes"] for s in scores)
    ratios = [r for s in scores for r in s["qty_ratios"]]
    return {
        "cases": len(scores), "dishes": D,
        "cookable_rate": round(sum(s["cookable"] for s in scores) / max(D, 1), 3),
        "ingredient_recall": round(sum(s["ess_covered"] for s in scores) / max(sum(s["ess_total"] for s in scores), 1), 3),
        "allergen_violations": sum(len(s["violations"]) for s in scores),
        "qty_median_abs_err": round(statistics.median([abs(r - 1) for r in ratios]), 3) if ratios else None,
        "qty_within_30pct": round(sum(1 for r in ratios if abs(r - 1) <= QTY_BAND) / len(ratios), 3) if ratios else None,
        "qty_under_80pct": round(sum(1 for r in ratios if r < COVER_OK) / len(ratios), 3) if ratios else None,
        "extra_lines": sum(s["extra_lines"] for s in scores), "extra_eur": round(sum(s["extra_eur"] for s in scores), 2),
        "total_eur": round(sum(s["total_eur"] for s in scores), 2),
        "recipe_subs_unflagged": sum(s["recipe_subs_unflagged"] for s in scores),
        "gaps": sum(s["gaps"] for s in scores),
    }
