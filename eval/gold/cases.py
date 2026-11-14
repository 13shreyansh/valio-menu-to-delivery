"""Eval cases: what a hotel kitchen sends (menu text + covers + kitchen profile).

The agent only sees `kitchen` and the `services[].items[].text/covers/diet`. `dish` is the
gold recipe id used by the scorer. `disruptions` are applied by the eval harness to the
availability layer (seeded, deterministic) to test substitutions and late deliveries.
Dates are next week relative to the event (Mon 16 Nov 2026 ...).
"""

K_AURORA = {"name": "Hotel Aurora Helsinki (city hotel, 240 rooms)", "customer": "HC-1001", "segment": "hotel",
            "policy": {"lactose_free_dairy": True, "free_from": [], "strict_may_contain": False, "auto_approve_limit_eur": 1500,
                        "allow_substitutes": "same_ingredient_auto"}}
K_LAPLAND = {"name": "Fell Lodge Saariselkä (resort hotel)", "customer": "HC-1002", "segment": "hotel",
             "policy": {"lactose_free_dairy": True, "free_from": [], "strict_may_contain": False, "auto_approve_limit_eur": 800,
                         "allow_substitutes": "ask"}}
K_HARBOUR = {"name": "Harbour Hotel Turku (conference hotel)", "customer": "HC-1003", "segment": "hotel",
             "policy": {"lactose_free_dairy": True, "free_from": ["nuts", "peanuts"], "strict_may_contain": True, "auto_approve_limit_eur": 2000,
                         "allow_substitutes": "same_ingredient_auto"}}
K_SPA = {"name": "Lakeside Spa Hotel Tampere", "customer": "HC-1004", "segment": "hotel",
         "policy": {"lactose_free_dairy": False, "free_from": [], "strict_may_contain": False, "auto_approve_limit_eur": 1200,
                     "allow_substitutes": "same_ingredient_auto"}}

def it(dish, text, covers, diet=()):
    return {"dish": dish, "text": text, "covers": covers, "diet": list(diet)}

CASES = [
 # ---------------- DEV ----------------
 {"id": "dev-aurora-mon", "split": "dev", "kitchen": K_AURORA, "services": [
   {"date": "2026-11-17", "meal": "lunch buffet", "items": [
     it("lohikeitto", "Lohikeitto (creamy salmon soup)", 140),
     it("lihapullat", "Lihapullat, kermakastike, perunamuusi, puolukka", 160),
     it("lentil_curry", "Vegan red lentil curry w/ rice", 60, ["vegan"])]}]},
 {"id": "dev-aurora-breakfast", "split": "dev", "kitchen": K_AURORA, "services": [
   {"date": "2026-11-18", "meal": "breakfast", "items": [
     it("scrambled_eggs", "Scrambled eggs", 220), it("oat_porridge", "Oat porridge + berries", 150),
     it("yoghurt_berries", "Greek yoghurt, berries, honey", 120), it("greek_yog_breakfast_eggs", "Boiled eggs", 120)]}]},
 {"id": "dev-lapland-dinner", "split": "dev", "kitchen": K_LAPLAND, "services": [
   {"date": "2026-11-19", "meal": "dinner", "items": [
     it("karjalanpaisti", "Karjalanpaisti & perunamuusi", 90), it("pikeperch", "Kuha, tilli-voikastike, perunat, porkkanat", 70),
     it("oven_pancake", "Pannukakku, mansikkahillo, kermavaahto", 150)]}]},
 {"id": "dev-harbour-conf", "split": "dev", "kitchen": K_HARBOUR, "services": [
   {"date": "2026-11-18", "meal": "conference lunch", "items": [
     it("caesar", "Chicken caesar salad", 200), it("mushroom_risotto", "Mushroom risotto (veg)", 80, ["vegetarian"]),
     it("chicken_curry", "Chicken curry, basmati", 200)]},
   {"date": "2026-11-19", "meal": "conference lunch", "items": [
     it("bolognese", "Spaghetti bolognese", 220), it("veg_soup", "Vegetable soup (vegan)", 60, ["vegan"])]}]},
 {"id": "dev-spa-dinner", "split": "dev", "kitchen": K_SPA, "services": [
   {"date": "2026-11-20", "meal": "à la carte week", "items": [
     it("pepper_steak", "Sirloin, pepper sauce, roast potatoes, green beans", 60), it("oven_salmon", "Oven salmon, lemon, root veg", 70),
     it("shrimp_pasta", "Garlic shrimp pasta", 40)]}]},
 {"id": "dev-aurora-thursday", "split": "dev", "kitchen": K_AURORA, "services": [
   {"date": "2026-11-19", "meal": "lunch buffet", "items": [
     it("hernekeitto", "Hernekeitto (pea soup)", 150), it("oven_pancake", "Pannukakku & hillo & kermavaahto", 150),
     it("makaronilaatikko", "Makaronilaatikko", 120)]}]},
 {"id": "dev-lapland-lunch", "split": "dev", "kitchen": K_LAPLAND, "services": [
   {"date": "2026-11-17", "meal": "lunch", "items": [
     it("kanakeitto", "Kanakeitto", 80), it("chili", "Chili con carne, rice, sour cream", 90), it("burger", "Cheeseburger", 60)]},
   {"date": "2026-11-18", "meal": "lunch", "items": [
     it("schnitzel", "Porsaanleike, paistetut perunat", 80), it("mashed_side", "Perunamuusi (side)", 40)]}]},
 {"id": "dev-aurora-gf", "split": "dev", "kitchen": K_AURORA, "services": [
   {"date": "2026-11-20", "meal": "gala dinner", "items": [
     it("lohikeitto", "Salmon soup, gluten-free", 180, ["gluten-free"]), it("pepper_steak", "Beef sirloin w/ pepper sauce, potatoes, beans (GF)", 180, ["gluten-free"]),
     it("lihapullat", "Meatballs, cream sauce, mash, lingonberries — GLUTEN-FREE version", 40, ["gluten-free"])]}]},
 # perturbed dev variants (same menus, disrupted supply)
 {"id": "dev-aurora-mon-stockout", "split": "dev", "base": "dev-aurora-mon", "disruptions": [
   {"ingredient": "salmon", "type": "stockout", "share": 0.7}, {"ingredient": "cream", "type": "stockout", "share": 0.6}]},
 {"id": "dev-harbour-conf-late", "split": "dev", "base": "dev-harbour-conf", "disruptions": [
   {"ingredient": "chicken_fillet", "type": "late", "share": 0.7}, {"ingredient": "romaine", "type": "stockout", "share": 1.0}]},
 # ---------------- HELD-OUT ----------------
 {"id": "ho-lapland-week", "split": "heldout", "kitchen": K_LAPLAND, "services": [
   {"date": "2026-11-18", "meal": "dinner", "items": [
     it("poronkaristys", "Poronkäristys, perunamuusi, puolukka", 110), it("berry_pie", "Mustikkapiirakka & vaniljakastike", 110),
     it("tomato_soup", "Tomato & basil soup (vegan)", 30, ["vegan"])]}]},
 {"id": "ho-harbour-conf", "split": "heldout", "kitchen": K_HARBOUR, "services": [
   {"date": "2026-11-17", "meal": "conference lunch", "items": [
     it("lasagne", "Beef lasagne", 180), it("vegan_bolognese", "Härkis bolognese (vegan)", 60, ["vegan"]), it("greek_salad", "Greek salad", 120)]},
   {"date": "2026-11-18", "meal": "conference lunch", "items": [
     it("green_curry", "Thai green curry, chicken, jasmine rice", 200), it("caesar_wrap", "Chicken caesar wraps", 150)]}]},
 {"id": "ho-aurora-breakfast", "split": "heldout", "kitchen": K_AURORA, "services": [
   {"date": "2026-11-19", "meal": "breakfast", "items": [
     it("omelette", "Ham & cheese omelette station", 160), it("salmon_sandwich", "Smoked salmon & cream cheese sandwiches", 120)]}]},
 {"id": "ho-spa-dinner", "split": "heldout", "kitchen": K_SPA, "services": [
   {"date": "2026-11-20", "meal": "dinner", "items": [
     it("pork_mushroom", "Pork tenderloin, creamy mushroom sauce, potatoes", 70), it("stroganoff", "Boeuf stroganoff & rice", 60),
     it("halloumi_salad", "Grilled halloumi salad (veg)", 30, ["vegetarian"]), it("fish_chips", "Fish & chips", 50)]}]},
 {"id": "ho-harbour-conf-stockout", "split": "heldout", "base": "ho-harbour-conf", "disruptions": [
   {"ingredient": "minced_meat", "type": "stockout", "share": 0.7}, {"ingredient": "coconut_milk", "type": "late", "share": 0.8}]},
 {"id": "ho-spa-dinner-stockout", "split": "heldout", "base": "ho-spa-dinner", "disruptions": [
   {"ingredient": "pork_fillet", "type": "stockout", "share": 0.8}, {"ingredient": "halloumi", "type": "stockout", "share": 1.0}]},
]

def resolve(case):
    if "base" in case:
        base = next(c for c in CASES if c["id"] == case["base"])
        return {**base, **{k: v for k, v in case.items() if k != "base"}}
    return case
