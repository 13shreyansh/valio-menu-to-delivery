"""Build public/eval.json (the "How we test it" tab) from eval run summaries. Numbers only, no Valio data.

  python scripts/build_eval_page.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "eval" / "runs"

MENU_RUNS = [("base-bm25", "Floor: keyword top-1, no LLM pick, no guardrails"),
             ("base-noguard", "Full agent with the allergen filter switched off"),
             ("v0", "First full agent"),
             ("v1", "Prepared forms accepted (diced onion, liquid egg); only salt, pepper, oil and water treated as pantry"),
             ("v2", "Pack size from the printed size when the price API agrees; exact quantities for direct requests")]
REQ_RUNS = [("r0", "First run"),
            ("r1", "Grader fix: a safe alternative held for sign-off counts as a stop"),
            ("r2", "Bug fix: direct requests now keep exact quantities and the cheapest-viable rule"),
            ("r3", "Harder set: total salmon stock-out, 2,000 L over the limit"),
            ("r3-k3", "Same, 3 fresh LLM samples per case (pass^3)")]


def load(name):
    p = RUNS / name / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


def pct(x):
    return "" if x is None else f"{x * 100:.0f}%"


def main():
    rows = []
    for name, why in MENU_RUNS:
        s = load(name)
        if not s:
            continue
        rows.append(f'<tr{" class=hi" if name == MENU_RUNS[-1][0] else ""}><td>{name}<br><span class=muted>{why}</span></td>'
                    f'<td>{round(s["cookable_rate"] * s["dishes"])}/{s["dishes"]} ({pct(s["cookable_rate"])})</td><td>{pct(s["ingredient_recall"])}</td>'
                    f'<td>{s["allergen_violations"]}</td><td>{pct(s["qty_within_30pct"])}</td><td>{s["extra_lines"]}</td>'
                    f'<td>{s.get("recipe_subs_unflagged", 0)}</td></tr>')
    menu_tbl = ("<table class=evtable><tr><th>Version</th><th>Dishes cookable</th><th>Ingredient recall</th>"
                "<th>Allergen/diet violations</th><th>Qty within ±30%</th><th>Extra lines</th><th>Unflagged recipe swaps</th></tr>"
                + "".join(rows) + "</table>")
    ho = load("heldout-final")
    ho_html = (f'<p><b>Held-out</b> (6 cases, 23 dishes from 14 recipe cards never seen while tuning, run once on the frozen version): '
               f'{pct(ho["cookable_rate"])} cookable, {pct(ho["ingredient_recall"])} ingredient recall, '
               f'{ho["allergen_violations"]} allergen violations.</p>') if ho else \
        '<p class=muted>Held-out split: runs once, on the frozen version.</p>'

    rrows = []
    for name, why in REQ_RUNS:
        s = load(name)
        if not s:
            continue
        k = s["k"]
        b = s["by_expected"]
        rrows.append(f'<tr{" class=hi" if name == REQ_RUNS[-1][0] else ""}><td>{name}<br><span class=muted>{why}</span></td>'
                     f'<td>{k}</td><td>{pct(s["pass_at_1"])}</td><td>{pct(s.get(f"pass_pow_{k}"))}</td>'
                     f'<td>{b.get("auto", "")}</td><td>{b.get("escalate", "")}</td><td>{b.get("refuse", "")}</td><td>{s["false_auto"]}</td></tr>')
    req_tbl = ("<table class=evtable><tr><th>Run</th><th>k</th><th>pass@1</th><th>pass^k</th><th>Auto</th><th>Escalate</th>"
               "<th>Refuse</th><th>False auto-approvals</th></tr>" + "".join(rrows) + "</table>")
    last = load(REQ_RUNS[-1][0]) or load("r3")
    cases = ""
    if last:
        cases = "<table class=evtable><tr><th>Request case</th><th>Expected</th><th>Decisions</th><th>Passed</th></tr>" + "".join(
            f'<tr><td>{r["id"]}</td><td>{r["expected"]}</td><td>{", ".join(r["decisions"])}</td><td>{r["passes"]}/{r["k"]}</td></tr>'
            for r in last["rows"]) + "</table>"

    html = f"""<p class=eyebrow>Evaluation</p><h2>How we test it</h2>
<p>Valio's booth told us what success means: <b>when the delivery arrives, the kitchen can cook the whole menu</b>, and the agent never
commits to something a person should decide. Both evals below are graded by code, not by an LLM. A scorer written separately from the
agent re-derives allergen violations from Valio's raw GS1 codes and re-checks availability through the API.</p>
<h3>1 · Menu → cart</h3>
<p class=muted>39 hand-written recipe cards (grams per portion, essential or not, allowed swaps), 124 gold ingredient rules over Valio's
category codes, 10 dev cases + 6 held-out, including stock-outs and late deliveries. A dish is <i>cookable</i> if every essential
component is bought at ≥ 80% of the gold quantity, arrives by the service date, and breaks no allergen rule.</p>
{menu_tbl}
{ho_html}
<h3>2 · Request → commitment → approval</h3>
<p class=muted>13 free-text buyer requests in the style of Valio's handout ("1,000 litres of lactose-free milk by Monday"),
balanced between cases where the agent should act alone (7) and cases where it must stop (3 escalate, 3 refuse: a peanut order
for a nut-free kitchen, every acceptable milk arriving late, a total salmon stock-out). Pass = right product, right quantity,
on time, right approval call. <b>pass^k</b> means all k fresh runs pass.</p>
{req_tbl}
{cases}
<h3>What still fails</h3>
<p>Fresh dill when it is out of stock, a few picks where our gold rules and the agent disagree (ham in an unusual category, burger
patties for "mince"), and two quantities just under the 80% bar. A chef grades the disputed ones in <code>eval/spot_checks.csv</code>
before any gold rule changes. Full ledger: <code>eval/METRICS_LOG.md</code> on GitHub.</p>"""
    (ROOT / "public" / "eval.json").write_text(json.dumps({"html": html}, ensure_ascii=False))
    print("wrote public/eval.json", len(html))


if __name__ == "__main__":
    main()
