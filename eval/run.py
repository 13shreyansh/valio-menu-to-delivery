"""Run the agent on eval cases and score it.

  python -m eval.run --split dev --name v1            # full agent
  python -m eval.run --split dev --name base --variant bm25_top1
  python -m eval.run --split heldout --name v1-final  # only when a version is frozen (see README)
"""
import argparse, json, sys, time
from pathlib import Path

from chefagent import llm
from chefagent.catalog import load
from chefagent.planner import Planner
from chefagent.valio_api import ValioAPI, Disruptions
from eval.gold.cases import CASES, resolve
from eval.gold.ingredients import I
from eval.score import score_case, summarize, gold_match

ROOT = Path(__file__).resolve().parent


def disruptions_for(case, cat):
    rules = []
    for d in case.get("disruptions", []):
        ids = [p["id"] for p in cat.food if gold_match(p, d["ingredient"])]
        rules.append({"type": d["type"], "share": d["share"], "product_ids": ids})
    return Disruptions(rules)


class Bm25Top1(Planner):
    """Baseline: same recipe expansion, but take the top lexical hit, no LLM pick, no guardrails."""
    def candidates(self, need):
        out = []
        for p, s in self.cat.search(need["ingredient"] + " " + " ".join(need.get("search", [])[:2]), k=5):
            out.append(p)
        return out, []

    def pick(self, need, cands):
        return [c["id"] for c in cands[:3]], "top lexical hits"


class NoGuardrails(Planner):
    def candidates(self, need):
        import chefagent.planner as pl
        orig = pl.product_violations
        pl.product_violations = lambda *a, **k: []
        try:
            return super().candidates(need)
        finally:
            pl.product_violations = orig


VARIANTS = {"full": Planner, "bm25_top1": Bm25Top1, "no_guardrails": NoGuardrails}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--name", required=True)
    ap.add_argument("--variant", default="full")
    ap.add_argument("--cases", default="")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    if args.split == "heldout" and not (ROOT / "FROZEN").exists():
        sys.exit("Held-out runs need eval/FROZEN (the frozen version tag) so held-out results cannot steer tuning.")
    cat = load()
    out_dir = ROOT / "runs" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [resolve(c) for c in CASES if c["split"] == args.split and (not args.cases or c["id"] in args.cases.split(","))]
    scores = []
    t0 = time.time()
    for case in cases:
        api = ValioAPI(customer=case["kitchen"]["customer"], disruptions=disruptions_for(case, cat))
        services = [{"date": s["date"], "meal": s.get("meal", ""),
                     "items": [{"text": i["text"], "covers": i["covers"], "diet": i["diet"]} for i in s["items"]]}
                    for s in case["services"]]
        planner = VARIANTS[args.variant](api, case["kitchen"], model=args.model)
        t = time.time()
        order = planner.plan(services)
        sc = score_case(case, order, cat, api)
        sc["seconds"] = round(time.time() - t, 1)
        scores.append(sc)
        (out_dir / f"{case['id']}.order.json").write_text(json.dumps(order, ensure_ascii=False, indent=1, default=list))
        (out_dir / f"{case['id']}.score.json").write_text(json.dumps(sc, ensure_ascii=False, indent=1))
        print(f"{case['id']:28s} cookable {sc['cookable']}/{sc['dishes']}  recall {sc['ess_covered']}/{sc['ess_total']}  "
              f"viol {len(sc['violations'])}  extra {sc['extra_lines']}  €{sc['total_eur']:.0f}  {sc['seconds']}s", flush=True)
    summ = summarize(scores)
    summ.update({"name": args.name, "variant": args.variant, "split": args.split, "model": args.model or llm.MODEL,
                 "llm": dict(llm.STATS), "seconds": round(time.time() - t0, 1)})
    (out_dir / "summary.json").write_text(json.dumps(summ, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
