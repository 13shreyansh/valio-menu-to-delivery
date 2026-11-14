"""Menu -> recipes -> ingredient needs -> Valio products -> cart grouped by delivery date.

The LLM does the culinary judgement (what a dish needs, which catalogue item is the right
one). Everything that must be trusted is plain code: allergen/diet guardrails, quantities
and pack rounding, price/stock lookups, delivery dates, the approval policy and the audit log.
"""
import datetime as dt
import json, math, re
from concurrent.futures import ThreadPoolExecutor

from . import llm
from .catalog import load as load_catalog
from .guardrails import product_violations
from .policy import apply_policy

RECIPE_SYSTEM = """You are the head chef and purchasing manager of a hotel kitchen in Finland.
You turn menu lines into exact purchasing needs for Valio Aimo, a Finnish foodservice wholesaler.
Be practical: use what a professional Finnish kitchen buys (e.g. pre-cut or frozen vegetables are fine,
mashed potato can be made from peeled potatoes). Quantities are AS-BOUGHT grams per portion
(liquids in ml), for a normal hotel buffet/dinner portion. Do not list water.
Mark ONLY salt, ground black/white pepper, cooking oil and water as role "pantry" (always in stock).
Everything else the dish needs (spices that define it, stock, sugar, flour, herbs) must be listed and bought. Respect dish diet tags (vegan, vegetarian, gluten-free...) in your ingredient choice."""

RECIPE_PROMPT = """Menu line: "{text}"
Diet tags for this line: {diet}
Kitchen: {kitchen}

Return JSON: {{"dish": short English dish name,
 "components": [{{"ingredient": generic English ingredient name (e.g. "salmon fillet", "cooking cream"),
   "search": [3-6 short catalogue search phrases, in English AND Finnish, e.g. "salmon fillet", "lohifilee", "lohi"],
   "grams_per_portion": number, "role": "main"|"side"|"sauce"|"garnish"|"pantry",
   "form": "fresh"|"frozen"|"canned"|"dry"|"dairy"|"any",
   "notes": optional short constraint, e.g. "must be gluten-free"}}]}}
Every component a cook needs to make this line must be listed once (combine duplicates)."""

PICK_SYSTEM = """You are a purchasing assistant for a hotel kitchen buying from Valio Aimo's catalogue.
Pick catalogue products that a chef would accept for the requested ingredient in this dish.
Reject prepared dishes, sauces, snacks or flavoured variants when the plain ingredient is needed,
and reject a different ingredient (e.g. smoked salmon for raw salmon). Professional kitchens happily buy
prepared forms of the SAME ingredient: peeled, diced, sliced, pre-cut, frozen or canned vegetables, liquid egg,
UHT dairy, frozen fish fillets. Accept those unless the dish clearly needs the whole raw item.
Prefer foodservice pack sizes that fit the needed quantity. Rank good -> better -> best is NOT needed; rank by how well it fits."""

PICK_PROMPT = """Ingredient needed: {ingredient} (form: {form}{notes})
Used in: {dishes}
Total needed: {qty:.2f} {unit} for delivery {date}

Candidates (id | name | pack | storage):
{cands}

Return JSON: {{"acceptable": [ids of ALL candidates a chef would accept, best first, max 6],
 "reason": one short sentence}}. If none is acceptable return an empty list."""

SUB_PROMPT = """The kitchen cannot get "{ingredient}" for: {dishes} (diet tags: {diet}).
Reason: {why}. Suggest up to 2 recipe-compatible substitute ingredients a chef would accept
for these dishes (keep the dish recognisable and respect the diet tags).
Return JSON: {{"substitutes": [{{"ingredient": name, "search": [3-5 English+Finnish search phrases],
 "grams_per_portion_factor": number (1.0 = same weight), "tradeoff": one short sentence for the chef}}]}}"""


def _today():
    return dt.date(2026, 11, 14)


def delivery_date_for(service_date: str) -> str:
    """Kitchens want goods the day before service (fresh, time to prep)."""
    d = dt.date.fromisoformat(service_date) - dt.timedelta(days=1)
    if d.weekday() == 6:  # no Sunday deliveries
        d -= dt.timedelta(days=1)
    return d.isoformat()


def norm_key(s):
    return re.sub(r"[^a-z]+", " ", s.lower()).strip()


class Planner:
    def __init__(self, api, kitchen, log=None, model=None, k_retrieve=30):
        self.cat = load_catalog()
        self.api = api
        self.kitchen = kitchen
        self.policy = kitchen.get("policy", {})
        self.model = model
        self.k = k_retrieve
        self.audit = log if log is not None else []

    # ---------------------------------------------------------------- audit
    def log(self, actor, action, detail, rule=None, **extra):
        self.audit.append({"actor": actor, "action": action, "detail": detail, "rule": rule, **extra})

    # ---------------------------------------------------------------- 1. recipes
    def expand(self, item):
        if item.get("direct"):
            # a product request ("1,000 litres of lactose-free milk by Monday"), not a dish
            qty = float(item.get("qty") or 0)
            comp = {"ingredient": item.get("ingredient") or item["text"], "search": item.get("search") or [],
                    "grams_per_portion": qty * 1000.0, "role": "main", "form": "any", "notes": item.get("notes", "")}
            self.log("agent", "read_request", f'"{item["text"]}" -> {qty:g} {item.get("unit","kg")} of {comp["ingredient"]}',
                     menu_item=item["idx"])
            return item["text"], [comp]
        out = llm.ask_json(RECIPE_PROMPT.format(text=item["text"], diet=", ".join(item.get("diet") or []) or "none",
                                                 kitchen=self.kitchen["name"]), system=RECIPE_SYSTEM, model=self.model)
        comps = [c for c in out.get("components", []) if c.get("ingredient")]
        self.log("agent", "expand_recipe", f'"{item["text"]}" -> {len(comps)} ingredients',
                 menu_item=item["idx"], components=[(c["ingredient"], c.get("grams_per_portion")) for c in comps])
        return out.get("dish", item["text"]), comps

    # ---------------------------------------------------------------- 2. retrieval
    def candidates(self, need):
        seen, out = set(), []
        queries = [need["ingredient"]] + list(need.get("search") or [])
        for q in queries:
            for p, s in self.cat.search(q, k=self.k):
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                out.append(p)
        allowed, blocked = [], []
        for p in out:
            v = product_violations(p, need["diet"], self.policy)
            (blocked if v else allowed).append((p, v))
        return [p for p, _ in allowed][: self.k * 2], blocked

    def pick(self, need, cands):
        if not cands:
            return [], "no candidates"
        lines = []
        for p in cands:
            pack = f'{p["pack"]:g} {p["pack_dim"]}' if p.get("pack") else "?"
            lines.append(f'{p["id"]} | {p["name"]} | {pack} per {p["sales_unit"]} | {p["temp"]}')
        out = llm.ask_json(PICK_PROMPT.format(ingredient=need["ingredient"], form=need.get("form", "any"),
                                              notes=(", " + need["notes"]) if need.get("notes") else "",
                                              dishes="; ".join(sorted(need["dishes"])), qty=need["kg"],
                                              unit="kg (or litres)", date=need["date"], cands="\n".join(lines)),
                           system=PICK_SYSTEM, model=self.model)
        ids = [str(i) for i in out.get("acceptable", []) if self.cat.get(str(i))]
        ids = [i for i in ids if any(i == p["id"] for p in cands)]  # never trust ids outside the guarded list
        return ids, out.get("reason", "")

    # ---------------------------------------------------------------- 3. quantities
    def pack_size(self, p, price):
        if p["sales_unit"] == "KG":
            return 1.0, "unit is kg"
        if price and not price.get("error") and price.get("comparison_price"):
            ratio = price["unit_price"] / price["comparison_price"]
            # the comparison price is rounded to cents, so the ratio is approximate: when the pack size
            # printed on the product agrees within 3%, trust the printed size (10 kg, not 9.98 kg)
            if p.get("pack") and abs(p["pack"] - ratio) <= 0.03 * p["pack"]:
                return p["pack"], "product pack size, confirmed by price API"
            return round(ratio, 4), "price API (unit / comparison price)"
        if p.get("pack"):
            return p["pack"], "catalogue name/GS1 estimate"
        return None, "unknown"

    @staticmethod
    def units_for(kg, pack, sales_unit, exact=False):
        """exact=True for a direct request: the buyer's quantity is a commitment, never round below it."""
        if sales_unit == "KG":
            return round(math.ceil(kg * 10 - 1e-9) / 10, 1)
        return max(1, math.ceil(kg / pack - (1e-9 if exact else 0.03)))  # menus: 3% tolerance before opening another pack

    # ---------------------------------------------------------------- 4. choose with price + availability
    def choose(self, need, ranked_ids):
        """Return (choice dict or None, tried list). Tries ranked products, then Valio's own
        substitution links, in order; first one orderable by the delivery date wins."""
        tried = []
        if not ranked_ids:
            return None, tried
        ids = list(ranked_ids)
        for pid in list(ranked_ids):
            for s in self.cat.get(pid).get("substitutes", []):
                sp = self.cat.get(s)
                if sp and s not in ids and not product_violations(sp, need["diet"], self.policy):
                    ids.append(s)
        ids = ids[:8]  # quote only the shortlist (Valio: never query prices for everything)
        avail = self.api.availability(need["date"], ids)
        price = self.api.price(need["date"], ids)
        viable = []
        for rank, pid in enumerate(ids):
            a, pr, p = avail.get(pid, {}), price.get(pid, {}), self.cat.get(pid)
            reason = None
            if not a.get("orderable"):
                reason = "not orderable" + (" (sales block)" if a.get("model") else " (no delivery date)")
            elif a.get("available_date") and a["available_date"] > need["date"]:
                reason = f'earliest delivery {a["available_date"]} is after {need["date"]}'
            elif pr.get("error"):
                reason = "no price"
            pack, pack_src = self.pack_size(p, pr)
            if not reason and not pack:
                reason = "unknown pack size"
            if reason:
                tried.append({"id": pid, "name": p["name"], "why": reason})
                continue
            units = self.units_for(need["kg"], pack, p["sales_unit"], exact=bool(need.get("direct")))
            if a.get("stock_known") and a.get("amount", 0) < units:
                tried.append({"id": pid, "name": p["name"], "why": f'only {a["amount"]:g} {p["sales_unit"]} in stock'})
                continue
            viable.append({"product": p, "rank": rank, "valio_link": pid not in ranked_ids, "pack": pack, "pack_source": pack_src,
                           "units": units, "price": pr, "avail": a, "cost": round(units * pr["unit_price"], 2),
                           "per_kg": round(pr["unit_price"] / pack, 2) if pack else None})
            if len(viable) >= 3:
                break
        if not viable:
            return None, tried
        if need.get("direct"):
            # explicit purchase request: cheapest acceptable option that arrives in time
            best = min(viable, key=lambda v: (v["cost"], v["rank"]))
        else:
            best = viable[0]  # best culinary fit first
        best["options"] = [{"id": v["product"]["id"], "name": v["product"]["name"], "units": v["units"],
                            "sales_unit": v["product"]["sales_unit"], "cost": v["cost"], "per_kg": v["per_kg"],
                            "reliability": v["product"].get("reliability"), "co2_per_kg": v["product"].get("co2_per_kg"),
                            "stock_known": v["avail"].get("stock_known"), "chosen": v is best} for v in viable]
        return best, tried

    # ---------------------------------------------------------------- main
    def plan(self, services):
        items = []
        for s in services:
            for it in s["items"]:
                items.append({**it, "idx": len(items), "date": s["date"], "meal": s.get("meal", "")})
        self.log("kitchen", "submit_menu", f"{len(items)} menu lines, {sum(i['covers'] for i in items)} covers",
                 rule=None)
        with ThreadPoolExecutor(8) as ex:
            expanded = list(ex.map(self.expand, items))
        # aggregate needs per (ingredient, diet constraints, delivery date)
        needs = {}
        for it, (dish, comps) in zip(items, expanded):
            it["dish_name"] = dish
            it["components"] = comps
            for c in comps:
                if c.get("role") == "pantry":
                    continue
                grams = float(c.get("grams_per_portion") or 0)
                if grams <= 0:
                    continue
                date = it["date"] if it.get("direct") else delivery_date_for(it["date"])
                key = (norm_key(c["ingredient"]), tuple(sorted(it.get("diet") or [])), date)
                n = needs.setdefault(key, {"ingredient": c["ingredient"], "search": list(c.get("search") or []),
                                           "form": c.get("form", "any"), "notes": c.get("notes", ""),
                                           "diet": list(it.get("diet") or []), "date": date, "kg": 0.0,
                                           "dishes": set(), "alloc": [], "optional": True,
                                           "direct": bool(it.get("direct"))})
                if c.get("role") != "garnish":
                    n["optional"] = False
                kg = grams * (1 if it.get("direct") else it["covers"]) / 1000.0
                n["kg"] += kg
                n["dishes"].add(dish)
                n["alloc"].append({"item": it["idx"], "ingredient": c["ingredient"], "kg": round(kg, 3)})
                for s in c.get("search") or []:
                    if s not in n["search"]:
                        n["search"].append(s)
        needs = list(needs.values())
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(self.resolve_need, needs))
        lines, gaps = [], []
        for n, (line, gap) in zip(needs, results):
            if line:
                lines.append(line)
            if gap:
                gaps.append(gap)
        lines = self.merge_lines(lines)
        order = apply_policy(lines, gaps, self.kitchen, self.audit)
        order["menu"] = [{"idx": it["idx"], "text": it["text"], "dish": it["dish_name"], "covers": it["covers"],
                          "date": it["date"], "meal": it["meal"], "diet": it.get("diet", []),
                          "components": it["components"], "direct": bool(it.get("direct")),
                          "ingredient": it.get("ingredient"), "qty": it.get("qty"), "unit": it.get("unit")} for it in items]
        return order

    def merge_lines(self, lines):
        """Two dishes needing 'onion' and 'diced onion' may land on the same product: one line, summed."""
        merged = {}
        for l in lines:
            k = (l["product_id"], l["delivery_date"])
            if k not in merged:
                merged[k] = l
                continue
            m = merged[k]
            m["need_kg"] = round(m["need_kg"] + l["need_kg"], 3)
            m["allocations"] += l["allocations"]
            m["dishes"] = sorted(set(m["dishes"]) | set(l["dishes"]))
            if l["ingredient"].lower() not in m["ingredient"].lower():
                m["ingredient"] += " / " + l["ingredient"]
            m["substitution"] = m["substitution"] or l["substitution"]
            m["units"] = self.units_for(m["need_kg"], m["pack_kg"], m["sales_unit"], exact=bool(m.get("direct") or l.get("direct")))
            m["ordered_kg"] = round(m["units"] * m["pack_kg"], 3)
            m["line_total"] = round(m["units"] * (m["unit_price"] or 0), 2)
            self.log("agent", "merge_lines", f'{m["name"]}: combined needs for {", ".join(m["dishes"])} into one line', product=m["product_id"])
        return list(merged.values())

    def resolve_need(self, need):
        cands, blocked = self.candidates(need)
        if blocked:
            self.log("guardrail", "filter_candidates", f'{need["ingredient"]}: removed {len(blocked)} products that break allergen/diet rules',
                     rule="allergen_diet", examples=[(p["name"], v[0]) for p, v in blocked[:3]])
        ranked, why = self.pick(need, cands)
        self.log("agent", "match_product", f'{need["ingredient"]}: {len(ranked)} acceptable of {len(cands)} candidates. {why}',
                 ranked=ranked[:6])
        choice, tried = self.choose(need, ranked)
        substitution = None
        if choice and choice["rank"] > 0 and tried and not need.get("direct"):
            substitution = {"type": "same_ingredient" if not choice["valio_link"] else "valio_substitute",
                            "original": [t["name"] for t in tried], "why": "; ".join(f'{t["name"]}: {t["why"]}' for t in tried)}
        if not choice and not need.get("direct"):
            # same ingredient, other form: fresh herbs and citrus are often unorderable while frozen,
            # dried or juice forms are on the shelf. Tried before changing the recipe.
            base = [need["ingredient"]] + list(need.get("search") or [])[:3]
            forms = [f"{pre} {b}" for b in base for pre in ("frozen", "pakaste", "dried", "kuivattu")] + \
                    [f"{b} {suf}" for b in base[:2] for suf in ("juice", "mehu", "puree")]
            alt = {**need, "search": forms, "form": "any",
                   "notes": (need.get("notes", "") + " The fresh form cannot be delivered in time: frozen, dried, "
                             "juice or puree forms of exactly this ingredient are acceptable; other ingredients are not.").strip()}
            c3, _ = self.candidates(alt)
            fresh_ids = {t["id"] for t in tried}
            r3, _ = self.pick(alt, [c for c in c3 if c["id"] not in fresh_ids])
            choice, tried3 = self.choose(alt, r3)
            if choice:
                substitution = {"type": "same_ingredient", "original": [t["name"] for t in tried] or [need["ingredient"]],
                                "why": "fresh form not deliverable in time; same ingredient in another form"}
                self.log("agent", "other_form", f'{need["ingredient"]}: {choice["product"]["name"]} instead (fresh form not deliverable)',
                         rule="substitution")
        if not choice:
            # recipe-level substitution
            why = "no acceptable product" if not ranked else "; ".join(f'{t["name"]}: {t["why"]}' for t in tried[:3])
            sub = llm.ask_json(SUB_PROMPT.format(ingredient=need["ingredient"], dishes="; ".join(need["dishes"]),
                                                 diet=", ".join(need["diet"]) or "none", why=why), model=self.model)
            for s in sub.get("substitutes", [])[:2]:
                factor = float(s.get("grams_per_portion_factor") or 1.0)
                alt = {**need, "ingredient": s["ingredient"], "search": s.get("search", []), "kg": need["kg"] * factor,
                       "alloc": [{**a, "kg": round(a["kg"] * factor, 3)} for a in need["alloc"]], "notes": ""}
                c2, _ = self.candidates(alt)
                r2, _ = self.pick(alt, c2)
                choice, tried2 = self.choose(alt, r2)
                if choice:
                    orig_ing, need = need["ingredient"], alt
                    substitution = {"type": "recipe", "original": [orig_ing], "for_ingredient": s["ingredient"],
                                    "why": why, "tradeoff": s.get("tradeoff", "")}
                    self.log("agent", "recipe_substitute", f'{alt["ingredient"]} instead of unavailable ingredient for {", ".join(need["dishes"])}: {s.get("tradeoff","")}',
                             rule="substitution")
                    break
            if not choice:
                self.log("agent", "gap", f'{need["ingredient"]}: cannot source by {need["date"]} ({why})', rule="gap")
                return None, {"ingredient": need["ingredient"], "kg": round(need["kg"], 2), "date": need["date"],
                              "dishes": sorted(need["dishes"]), "why": why, "alloc": need["alloc"],
                              "optional": need.get("optional", False)}
        p, pr, a = choice["product"], choice["price"], choice["avail"]
        line = {"product_id": p["id"], "name": p["name"], "brand": p.get("brand", ""), "vendor": p.get("vendor", ""),
                "ingredient": need["ingredient"], "dishes": sorted(need["dishes"]), "diet": need["diet"],
                "delivery_date": need["date"], "available_date": a.get("available_date"), "closing_time": a.get("closing_time"),
                "sales_unit": p["sales_unit"], "units": choice["units"], "pack_kg": choice["pack"], "pack_source": choice["pack_source"],
                "need_kg": round(need["kg"], 3), "ordered_kg": round(choice["units"] * choice["pack"], 3),
                "unit_price": pr.get("unit_price"), "line_total": round(choice["units"] * pr.get("unit_price", 0), 2),
                "comparison_price": pr.get("comparison_price"), "comparison_unit": pr.get("comparison_unit"),
                "net_price": pr.get("net_price"), "stock_known": a.get("stock_known"), "stock_model": a.get("model"),
                "reliability": p.get("reliability"), "co2_per_kg": p.get("co2_per_kg"), "labels": p.get("labels", []),
                "contains": p["contains"], "may_contain": p["may_contain"], "temp": p["temp"],
                "allocations": need["alloc"], "substitution": substitution,
                "alternatives": [x for x in ranked[:4] if x != p["id"]], "options": choice.get("options", []), "direct": bool(need.get("direct"))}
        self.log("agent", "add_to_cart", f'{p["name"]} x {choice["units"]:g} {p["sales_unit"]} for {", ".join(sorted(need["dishes"]))}'
                 f' (need {need["kg"]:.2f} kg, pack {choice["pack"]:g} via {choice["pack_source"]})', product=p["id"])
        return line, None
