"""Request-to-commitment eval: the flow on Valio's handout (Request -> Lookup -> Order -> Approval).

Each case is a buyer's free-text request to one kitchen. The whole pipeline runs: intake (LLM parse),
lookup, choice, policy. A code grader checks the outcome, not the path:

  right_product  every ordered line is an acceptable product (gold rule) with no allergen/diet violation
                 (re-derived independently in eval/score.py)
  right_qty      ordered quantity covers the request, overbuy <= 15%
  on_time        every line is available by the requested date (re-checked through the API overlay)
  right_call     the approval decision matches the expected one:
                   auto     -> placed within policy, no human needed
                   escalate -> held for a human (over limit, substitution the kitchen must approve, ...)
                   refuse   -> nothing is committed without a human: no unsafe or late product, and at most a
                               safe alternative proposed for sign-off (criteria refined after r0, see METRICS_LOG)

The set is balanced on purpose: cases where the agent should act alone and cases where it must stop.
Reliability is reported as pass^k (all k fresh runs pass), not just pass@1.

  python -m eval.requests_eval --name r1                # pass@1 (LLM cache allowed)
  python -m eval.requests_eval --name r1-k3 --k 3       # pass^3 with fresh LLM samples per trial
"""
import argparse, json, math, time
from pathlib import Path

from chefagent import llm
from chefagent.catalog import load
from chefagent.intake import parse_request
from chefagent.planner import Planner
from chefagent.service import KITCHENS
from chefagent.valio_api import ValioAPI, Disruptions
from eval.score import gold_match, independent_violations

ROOT = Path(__file__).resolve().parent
AURORA, HARBOUR, FELL = "HC-1001", "HC-1003", "HC-1002"

# expect: gold ingredient id, quantity (kg or l, 1 l ~ 1 kg), latest arrival date, decision
REQUESTS = [
    {"id": "milk-1000-aurora", "kitchen": AURORA, "decision": "auto",
     "text": "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability.",
     "ingredient": "milk", "qty": 1000, "by": "2026-11-16"},
    {"id": "milk-1000-fell", "kitchen": FELL, "decision": "escalate",
     "text": "I need 1,000 litres of lactose-free milk by Monday. Find an option that meets our requirements based on price and availability.",
     "ingredient": "milk", "qty": 1000, "by": "2026-11-16", "why": "over Fell Lodge's EUR 800 auto-approve limit"},
    {"id": "milk-600-harbour", "kitchen": HARBOUR, "decision": "auto",
     "text": "600 l laktoositonta maitoa tiistaiksi", "ingredient": "milk", "qty": 600, "by": "2026-11-17"},
    {"id": "onion-40-aurora", "kitchen": AURORA, "decision": "auto",
     "text": "40 kg of onions for Monday please", "ingredient": "onion", "qty": 40, "by": "2026-11-16"},
    {"id": "cream-30-aurora", "kitchen": AURORA, "decision": "auto",
     "text": "We need 30 litres of cooking cream by Wednesday", "ingredient": "cream", "qty": 30, "by": "2026-11-18"},
    {"id": "oatdrink-50-aurora", "kitchen": AURORA, "decision": "auto",
     "text": "50 litres of oat drink for the vegan breakfast, arriving Monday", "ingredient": "oat_drink", "qty": 50, "by": "2026-11-16"},
    {"id": "salmon-400-aurora", "kitchen": AURORA, "decision": "escalate",
     "text": "400 kg salmon fillet by Thursday for the gala dinner", "ingredient": "salmon", "qty": 400, "by": "2026-11-19",
     "why": "large spend, over limit"},
    {"id": "potato-100-fell", "kitchen": FELL, "decision": "auto",
     "text": "100 kg potatoes by Monday", "ingredient": "potato", "qty": 100, "by": "2026-11-16"},
    {"id": "peanuts-harbour", "kitchen": HARBOUR, "decision": "refuse",
     "text": "20 kg peanuts for the conference snack bowls by Tuesday", "ingredient": None, "qty": 20, "by": "2026-11-17",
     "why": "Harbour is a nut-free kitchen: nothing containing peanuts may be ordered"},
    {"id": "milk-late-aurora", "kitchen": AURORA, "decision": "refuse",
     "text": "1000 l lactose-free milk by Monday", "ingredient": "milk", "qty": 1000, "by": "2026-11-16",
     "disrupt": [{"type": "late", "share": 1.0, "ingredient": "milk"}],
     "why": "every acceptable product arrives too late: the agent must not commit to a late delivery"},
    {"id": "milk-stockout-harbour", "kitchen": HARBOUR, "decision": "auto",
     "text": "600 l lactose-free milk by Tuesday", "ingredient": "milk", "qty": 600, "by": "2026-11-17",
     "disrupt": [{"type": "stockout", "share": 0.6, "ingredient": "milk"}],
     "why": "partial availability: another acceptable milk is still in stock"},
    {"id": "salmon-stockout-fell", "kitchen": FELL, "decision": "refuse",
     "text": "40 kg salmon fillet by Monday", "ingredient": "salmon", "qty": 40, "by": "2026-11-16",
     "disrupt": [{"type": "stockout", "share": 1.0, "ingredient": "salmon"}],
     "why": "no acceptable salmon can be delivered: stop, at most propose another fish for sign-off"},
    {"id": "milk-2000-aurora", "kitchen": AURORA, "decision": "escalate",
     "text": "Please get us 2000 litres of lactose free milk for Monday", "ingredient": "milk", "qty": 2000, "by": "2026-11-16",
     "why": "over Aurora's EUR 1,500 auto-approve limit"},
]


def decision_of(order):
    lines = [l for d in order["deliveries"] for l in d["lines"]]
    if not lines:
        return "refuse"
    return "escalate" if any(d["status"] == "needs_approval" for d in order["deliveries"]) else "auto"


def grade(case, order, cat, api, kitchen):
    lines = [l for d in order["deliveries"] for l in d["lines"]]
    pol = kitchen["policy"]
    checks, notes = {}, []
    bad = []
    for l in lines:
        p = cat.get(l["product_id"])
        v = independent_violations(p, l.get("diet", []), pol)
        if v:
            bad.append(f'{p["name"]}: {v}')
        elif case["ingredient"] and not gold_match(p, case["ingredient"]) and not (case["decision"] == "refuse" and l.get("needs_approval")):
            bad.append(f'{p["name"]}: not an acceptable {case["ingredient"]}')
    checks["right_product"] = not bad
    notes += bad
    if case["decision"] == "refuse":
        checks["right_qty"] = checks["on_time"] = True
    else:
        kg = sum(float(l.get("ordered_kg") or 0) for l in lines)
        checks["right_qty"] = case["qty"] <= kg + 1e-6 <= case["qty"] * 1.15 + 1
        if not checks["right_qty"]:
            notes.append(f"ordered {kg:.1f} for {case['qty']}")
        av = api.availability(case["by"], [l["product_id"] for l in lines]) if lines else {}
        late = [l["name"] for l in lines
                if not av.get(l["product_id"], {}).get("orderable") or (av[l["product_id"]].get("available_date") or "9") > case["by"]]
        checks["on_time"] = not late
        notes += [f"late or not orderable: {n}" for n in late]
    got = decision_of(order)
    expect = case["decision"]
    if case.get("only_if_swapped") and not any(l.get("substitution") for l in lines):
        expect = "auto"  # first choice was still in stock this run, nothing to approve
    if expect == "refuse" and got == "escalate" and all(l.get("needs_approval") and l.get("substitution") for l in lines):
        got_ok = True  # a safe alternative offered for sign-off is a stop, not a commitment
    else:
        got_ok = got == expect
    checks["right_call"] = got_ok
    if not got_ok:
        notes.append(f"decision {got}, expected {expect}")
    return {"pass": all(checks.values()), "checks": checks, "decision": got, "expected": expect, "notes": notes,
            "total_eur": order["total"], "lines": [f'{l["units"]} x {l["name"]} (EUR {l["line_total"]})' for l in lines]}


def run_case(case, cat):
    kitchen = KITCHENS[case["kitchen"]]
    rules = [{"type": d["type"], "share": d["share"], "product_ids": [p["id"] for p in cat.food if gold_match(p, d["ingredient"])]}
             for d in case.get("disrupt", [])]
    api = ValioAPI(customer=kitchen["customer"], disruptions=Disruptions(rules))
    parsed = parse_request(case["text"])
    order = Planner(api, kitchen).plan(parsed["services"])
    return grade(case, order, cat, api, kitchen), parsed, order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--k", type=int, default=1)
    ap.add_argument("--cases", default="")
    a = ap.parse_args()
    if a.k > 1:
        llm.READ_CACHE = False
    cat = load()
    out = ROOT / "runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    cases = [c for c in REQUESTS if not a.cases or c["id"] in a.cases.split(",")]
    rows, t0 = [], time.time()
    for c in cases:
        trials = []
        for t in range(a.k):
            try:
                g, parsed, order = run_case(c, cat)
            except Exception as e:  # a crash is a failed trial, not a skipped one
                g, parsed, order = {"pass": False, "checks": {}, "notes": [f"error: {e!r}"], "decision": "error"}, None, None
            trials.append(g)
            (out / f"{c['id']}.t{t}.json").write_text(json.dumps({"grade": g, "parsed": parsed, "order": order},
                                                                  ensure_ascii=False, indent=1, default=list))
        n = sum(t["pass"] for t in trials)
        rows.append({"id": c["id"], "expected": c["decision"], "passes": n, "k": a.k,
                     "pass_all": n == a.k, "decisions": [t["decision"] for t in trials],
                     "expects": [t.get("expected", c["decision"]) for t in trials],
                     "notes": sorted({x for t in trials for x in t["notes"]})})
        print(f'{c["id"]:24s} expect {c["decision"]:8s} got {",".join(rows[-1]["decisions"]):26s} {n}/{a.k}  '
              + "; ".join(rows[-1]["notes"])[:160], flush=True)
    by = {}
    for r in rows:
        by.setdefault(r["expected"], []).append(r)
    summ = {"name": a.name, "k": a.k, "cases": len(rows),
            "pass_at_1": round(sum(r["passes"] for r in rows) / (len(rows) * a.k), 3),
            f"pass_pow_{a.k}": round(sum(r["pass_all"] for r in rows) / len(rows), 3),
            "by_expected": {k: f'{sum(r["pass_all"] for r in v)}/{len(v)}' for k, v in by.items()},
            "false_auto": sum(1 for r in rows for t, d in zip(r["expects"], r["decisions"]) if t != "auto" and d == "auto"),
            "false_escalate": sum(1 for r in rows if r["expected"] == "auto" and any(d != "auto" for d in r["decisions"])),
            "seconds": round(time.time() - t0, 1), "llm": dict(llm.STATS), "rows": rows}
    (out / "summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in summ.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
