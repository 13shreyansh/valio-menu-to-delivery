"""Approval policy (the kitchen's mandate). Deterministic: decides which lines the agent may
place on its own and which wait for a human tap, and writes the reason to the audit log.

Rules (each one is named so the audit trail can cite it):
  R1 spend      : order total for a delivery above the kitchen's auto-approve limit -> human
  R2 substitute : any recipe-level substitute (different ingredient) -> human
                  same-ingredient swap (other brand/pack) -> auto if policy allows, else human
  R3 may_contain: product may contain an allergen the kitchen excludes (non-strict kitchens) -> human
  R4 pack       : pack size not confirmed by the price API -> human
  R5 gap        : an ingredient cannot be sourced by the delivery date -> the dish is flagged
  R6 cutoff     : order cut-off has passed for the requested delivery -> human (re-date)
"""
from collections import defaultdict


def apply_policy(lines, gaps, kitchen, audit):
    pol = kitchen.get("policy", {})
    limit = pol.get("auto_approve_limit_eur", 1000)
    for ln in lines:
        flags = []
        sub = ln.get("substitution")
        if sub:
            if sub["type"] == "recipe":
                flags.append({"rule": "R2", "text": f'Substitute ingredient: {ln["ingredient"]} ({sub.get("tradeoff","")})'})
            elif pol.get("allow_substitutes") != "same_ingredient_auto":
                flags.append({"rule": "R2", "text": f'Swapped product: first choice unavailable ({sub["why"][:120]})'})
        for a in pol.get("free_from", []):
            if a in ln["may_contain"]:
                flags.append({"rule": "R3", "text": f"May contain {a}"})
        if not ln["pack_source"].startswith("price API") and ln["sales_unit"] != "KG":
            flags.append({"rule": "R4", "text": f'Pack size estimated from catalogue ({ln["pack_kg"]:g} kg/L per {ln["sales_unit"]})'})
        ln["flags"] = flags
        ln["needs_approval"] = bool(flags)
    by_date = defaultdict(list)
    for ln in lines:
        by_date[ln["delivery_date"]].append(ln)
    deliveries = []
    for date in sorted(by_date):
        ls = sorted(by_date[date], key=lambda l: (l["temp"], l["name"]))
        total = round(sum(l["line_total"] for l in ls), 2)
        over = total > limit
        if over:
            audit.append({"actor": "policy", "action": "hold", "rule": "R1",
                          "detail": f"Delivery {date}: total €{total:.2f} is over the €{limit} auto-approve limit, needs a human tap"})
        n_flag = sum(1 for l in ls if l["needs_approval"])
        for l in ls:
            if l["needs_approval"]:
                audit.append({"actor": "policy", "action": "hold", "rule": ",".join(f["rule"] for f in l["flags"]),
                              "detail": f'{l["name"]}: ' + "; ".join(f["text"] for f in l["flags"])})
        deliveries.append({"date": date, "lines": ls, "total": total, "over_limit": over,
                           "status": "needs_approval" if (over or n_flag) else "auto_approved",
                           "co2_kg": round(sum((l.get("co2_per_kg") or 0) * l["ordered_kg"] for l in ls), 1)})
    for g in gaps:
        audit.append({"actor": "policy", "action": "gap", "rule": "R5",
                      "detail": f'Cannot source {g["ingredient"]} for {", ".join(g["dishes"])} by {g["date"]}: {g["why"][:160]}'})
    total = round(sum(d["total"] for d in deliveries), 2)
    audit.append({"actor": "policy", "action": "summary", "rule": None,
                  "detail": f"{len(lines)} lines in {len(deliveries)} deliveries, €{total:.2f} excl. VAT; "
                            f"{sum(1 for d in deliveries if d['status']=='auto_approved')} auto-approved, "
                            f"{sum(1 for d in deliveries if d['status']!='auto_approved')} waiting for approval; {len(gaps)} gaps"})
    return {"deliveries": deliveries, "gaps": gaps, "total": total, "audit": audit,
            "kitchen": kitchen["name"], "customer": kitchen.get("customer")}
