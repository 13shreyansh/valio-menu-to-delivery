"""Hard, deterministic product guardrails. The LLM never sees a product that breaks the
kitchen's allergen/diet rules, so it cannot pick one. (The eval re-checks this with an
independent checker in eval/score.py.)"""

MEAT_FISH_CATS = ("187", "188", "172", "4170", "4171", "4172", "21510", "21530", "18")
FRESH_DAIRY_CATS = {"10400", "10401", "10405", "10411", "10412", "10419", "10430", "10432", "10404"}
ANIMAL_ALLERGENS = {"milk", "egg", "fish", "crustaceans", "molluscs"}


def is_meat_or_fish(p):
    return p["category"].startswith(("187", "188", "172", "4170", "4171", "4172")) or p["category"] in ("21510", "21530")


def product_violations(p, diet=(), policy=None):
    """Return list of human-readable reasons this product may not be used for a dish
    with `diet` tags under kitchen `policy`. Empty list = allowed."""
    policy = policy or {}
    v = []
    diet = set(diet)
    contains, may = set(p["contains"]), set(p["may_contain"])
    strict = policy.get("strict_may_contain", False)
    for a in policy.get("free_from", []):
        if a in contains:
            v.append(f"contains {a} (kitchen is {a}-free)")
        elif strict and a in may:
            v.append(f"may contain {a} (kitchen is strictly {a}-free)")
    if "gluten-free" in diet:
        if "gluten" in contains:
            v.append("contains gluten (dish is gluten-free)")
        elif "gluten" in may and not p.get("gluten_free"):
            v.append("may contain gluten (dish is gluten-free)")
    if "vegan" in diet:
        if contains & ANIMAL_ALLERGENS:
            v.append("contains " + "/".join(sorted(contains & ANIMAL_ALLERGENS)) + " (dish is vegan)")
        if is_meat_or_fish(p) or (p["category"].startswith("10") and p["category"] not in ("10402", "10406", "10413", "10418", "10641", "10530", "10531", "10532", "10517", "10515", "10516", "10518")):
            if not p.get("vegan"):
                v.append("animal product (dish is vegan)")
        if p["category"] in ("22150",):
            v.append("honey (dish is vegan)")
    if "vegetarian" in diet and is_meat_or_fish(p):
        v.append("meat/fish (dish is vegetarian)")
    if "milk-free" in diet and "milk" in contains:
        v.append("contains milk (dish is milk-free)")
    if policy.get("lactose_free_dairy"):
        if p["category"] in FRESH_DAIRY_CATS and "milk" in contains and not p.get("lactose_free"):
            v.append("not lactose-free (kitchen serves lactose-free dairy)")
        elif p.get("lactose") and not p.get("lactose_free"):
            v.append("contains lactose (kitchen serves lactose-free dairy)")
    return v
