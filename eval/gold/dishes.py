"""Gold recipe cards (hand-authored, standard foodservice proportions).

Each component: accept = {ingredient_id: grams per portion (as bought)}. Any one of the
accepted ingredients satisfies the component; its grams set the expected quantity.
ess=False = pantry/garnish: not needed for "cookable", never penalised.
Liquids: 1 ml counted as 1 g.
"""

def C(accept, ess=True, subs=None):
    """subs = recipe-compatible substitutes: only count when the agent flags them for human approval."""
    return {"accept": accept, "ess": ess, "subs": subs or {}}

DISHES = [
 # ======================= DEV (26) =======================
 dict(id="lohikeitto", split="dev", name="Creamy salmon soup", fi="Lohikeitto", diet=[], components=[
   C({"salmon": 110}, subs={"white_fish": 110}), C({"potato": 150}), C({"cream": 60, "whipping_cream": 50}), C({"leek": 30, "onion": 30}),
   C({"carrot": 30}, False), C({"dill": 2}), C({"fish_stock": 8}, False), C({"butter": 5}, False)]),
 dict(id="karjalanpaisti", split="dev", name="Karelian hotpot with mashed potatoes", fi="Karjalanpaisti ja perunamuusi", diet=[], components=[
   C({"beef_stew_cut": 90}), C({"pork_stew_cut": 90}), C({"onion": 40}), C({"carrot": 30}, False), C({"allspice": 0.5}, False),
   C({"potato_mash": 200, "potato": 220}), C({"milk": 40}), C({"butter": 10})]),
 dict(id="lihapullat", split="dev", name="Meatballs in cream sauce, mashed potatoes, lingonberries", fi="Lihapullat kermakastikkeessa, perunamuusi, puolukka", diet=[], components=[
   C({"minced_meat": 120}), C({"breadcrumbs": 8}), C({"egg": 8}), C({"onion": 15}), C({"cream": 40, "whipping_cream": 35}),
   C({"potato_mash": 200, "potato": 220}), C({"milk": 30}), C({"lingonberry": 25}), C({"stock": 5}, False)]),
 dict(id="chicken_curry", split="dev", name="Chicken curry with basmati rice", fi="Broilericurry ja basmatiriisi", diet=[], components=[
   C({"chicken_fillet": 130, "chicken_thigh": 130, "chicken_any": 130}), C({"onion": 30}), C({"garlic": 3}, False), C({"curry_powder": 4}),
   C({"coconut_milk": 80, "cream": 70}), C({"tomato_canned": 50}, False), C({"rice": 75}), C({"ginger": 2}, False)]),
 dict(id="bolognese", split="dev", name="Spaghetti bolognese", fi="Spagetti bolognese", diet=[], components=[
   C({"minced_meat": 110}), C({"spaghetti": 100, "pasta": 100}), C({"tomato_canned": 100}), C({"onion": 30}), C({"carrot": 20}, False),
   C({"garlic": 3}, False), C({"tomato_paste": 10}, False), C({"parmesan": 10, "hard_cheese": 10}, False)]),
 dict(id="caesar", split="dev", name="Chicken Caesar salad", fi="Kana-caesarsalaatti", diet=[], components=[
   C({"romaine": 80, "lettuce": 80}), C({"chicken_fillet": 100, "chicken_any": 100}), C({"parmesan": 10}), C({"croutons": 15, "bread_roll": 20}),
   C({"caesar_dressing": 30, "mayonnaise": 25}), C({"bacon": 15}, False)]),
 dict(id="mushroom_risotto", split="dev", name="Mushroom risotto", fi="Sienirisotto", diet=["vegetarian"], components=[
   C({"risotto_rice": 80, "rice": 80}), C({"mushroom": 100}), C({"onion": 30}), C({"veg_stock": 10, "stock": 10}), C({"parmesan": 15, "hard_cheese": 15}),
   C({"butter": 10}), C({"cream": 20}, False)]),
 dict(id="lentil_curry", split="dev", name="Red lentil and spinach curry with rice (vegan)", fi="Linssicurry (vegaaninen)", diet=["vegan"], components=[
   C({"lentils": 70}), C({"coconut_milk": 80}), C({"onion": 30}), C({"tomato_canned": 80}), C({"garlic": 3}, False), C({"curry_powder": 4}),
   C({"rice": 75}), C({"spinach": 30}, False)]),
 dict(id="scrambled_eggs", split="dev", name="Scrambled eggs (breakfast buffet)", fi="Munakokkeli", diet=["vegetarian"], components=[
   C({"egg": 100}), C({"milk": 20, "cream": 20}), C({"butter": 5}), C({"chives": 1}, False)]),
 dict(id="oat_porridge", split="dev", name="Oat porridge with berries", fi="Kaurapuuro ja marjat", diet=["vegetarian"], components=[
   C({"porridge_oats": 40, "oats": 40}), C({"milk": 150}), C({"berries_frozen": 30, "jam": 25}), C({"butter": 5}, False), C({"salt": 1}, False)]),
 dict(id="yoghurt_berries", split="dev", name="Greek yoghurt with berries and honey", fi="Kreikkalainen jogurtti, marjat ja hunaja", diet=["vegetarian"], components=[
   C({"yoghurt_natural": 150}), C({"berries_frozen": 40}), C({"honey": 10}, False)]),
 dict(id="oven_pancake", split="dev", name="Oven pancake with jam and whipped cream", fi="Pannukakku, hillo ja kermavaahto", diet=["vegetarian"], components=[
   C({"milk": 150}), C({"egg": 30}), C({"flour": 40}), C({"sugar": 10}), C({"butter": 10}), C({"jam": 30}), C({"whipping_cream": 30})]),
 dict(id="pepper_steak", split="dev", name="Beef sirloin with pepper sauce, roast potatoes and green beans", fi="Naudan ulkofilee, pippurikastike, paahdetut perunat", diet=[], components=[
   C({"beef_steak": 180}), C({"potato": 200}), C({"cream": 50, "whipping_cream": 45}), C({"black_pepper": 2}, False), C({"butter": 10}, False),
   C({"green_beans": 80, "broccoli": 80})]),
 dict(id="pikeperch", split="dev", name="Pike-perch with dill butter sauce, potatoes and carrots", fi="Kuhaa, tilli-voikastike, perunat ja porkkanat", diet=[], components=[
   C({"white_fish": 150}), C({"potato": 200}), C({"butter": 20}), C({"cream": 40, "whipping_cream": 35}), C({"dill": 2}), C({"lemon": 5}, False),
   C({"carrot": 80, "root_veg": 80})]),
 dict(id="schnitzel", split="dev", name="Pork schnitzel with fried potatoes", fi="Porsaanleike ja paistetut perunat", diet=[], components=[
   C({"pork_fillet": 150}), C({"egg": 10}), C({"breadcrumbs": 20}), C({"flour": 10}, False), C({"potato": 200}), C({"lemon": 5}, False),
   C({"cooking_fat": 15}, False)]),
 dict(id="oven_salmon", split="dev", name="Oven-baked salmon with lemon and root vegetables", fi="Uunilohi ja juurekset", diet=[], components=[
   C({"salmon": 150}), C({"root_veg": 150, "carrot": 150}), C({"lemon": 5}), C({"dill": 1, "herb_fresh": 1}, False), C({"oil": 5}, False)]),
 dict(id="veg_soup", split="dev", name="Vegetable soup (vegan)", fi="Kasviskeitto (vegaaninen)", diet=["vegan"], components=[
   C({"frozen_veg_mix": 150, "root_veg": 150}), C({"potato": 80}), C({"veg_stock": 10}), C({"onion": 20}), C({"herb_fresh": 1, "parsley": 1}, False)]),
 dict(id="chili", split="dev", name="Chili con carne with rice and sour cream", fi="Chili con carne, riisi ja smetana", diet=[], components=[
   C({"minced_meat": 100}), C({"beans_canned": 60}), C({"tomato_canned": 100}), C({"onion": 30}), C({"garlic": 3}, False), C({"chili": 1}, False),
   C({"cumin": 1}, False), C({"rice": 75}), C({"sour_cream": 20}, False)]),
 dict(id="burger", split="dev", name="Cheeseburger", fi="Juustohampurilainen", diet=[], components=[
   C({"minced_meat": 150}), C({"burger_bun": 80}), C({"lettuce": 15}), C({"tomato_fresh": 30}), C({"hard_cheese": 20}), C({"red_onion": 15, "onion": 15}, False),
   C({"pickled_cucumber": 10}, False), C({"mayonnaise": 15}, False)]),
 dict(id="shrimp_pasta", split="dev", name="Creamy garlic shrimp pasta", fi="Valkosipulikatkarapupasta", diet=[], components=[
   C({"pasta": 100, "spaghetti": 100}), C({"shrimp": 80}), C({"garlic": 3}), C({"cream": 60, "whipping_cream": 50}), C({"parmesan": 10}, False), C({"spinach": 20}, False)]),
 dict(id="kanakeitto", split="dev", name="Chicken soup", fi="Kanakeitto", diet=[], components=[
   C({"chicken_any": 80, "chicken_fillet": 80, "chicken_thigh": 80}), C({"potato": 100}), C({"carrot": 40, "root_veg": 40}), C({"onion": 20, "leek": 20}),
   C({"stock": 10}), C({"parsley": 1, "herb_fresh": 1}, False)]),
 dict(id="hernekeitto", split="dev", name="Pea soup with ham (Thursday classic)", fi="Hernekeitto", diet=[], components=[
   C({"dried_peas": 70}), C({"ham": 40, "pork_stew_cut": 40}), C({"onion": 20}), C({"mustard": 10}, False), C({"stock": 5}, False)]),
 dict(id="makaronilaatikko", split="dev", name="Macaroni and minced meat casserole", fi="Makaronilaatikko", diet=[], components=[
   C({"pasta": 70}), C({"minced_meat": 70}), C({"onion": 15}), C({"egg": 25}), C({"milk": 120}), C({"hard_cheese": 10}, False)]),
 dict(id="pancakes_veg", split="dev", name="Vegetable patties? no",  fi="", diet=[], components=[], disabled=True),
 dict(id="mashed_side", split="dev", name="Mashed potatoes (side)", fi="Perunamuusi", diet=["vegetarian"], components=[
   C({"potato_mash": 200, "potato": 220}), C({"milk": 40}), C({"butter": 10})]),
 dict(id="greek_yog_breakfast_eggs", split="dev", name="Boiled eggs (breakfast)", fi="Keitetyt kananmunat", diet=["vegetarian"], components=[
   C({"egg": 60})]),

 # ======================= HELD-OUT (14) — do not inspect while tuning =======================
 dict(id="lasagne", split="heldout", name="Beef lasagne", fi="Lasagne", diet=[], components=[
   C({"lasagne_sheets": 50}), C({"minced_meat": 100}, subs={"plant_mince": 90}), C({"tomato_canned": 100}), C({"onion": 25}), C({"milk": 100}), C({"flour": 10}, False),
   C({"butter": 10}, False), C({"hard_cheese": 30, "mozzarella": 30})]),
 dict(id="poronkaristys", split="heldout", name="Sautéed reindeer with mashed potatoes and lingonberries", fi="Poronkäristys, perunamuusi ja puolukka", diet=[], components=[
   C({"reindeer": 130}), C({"potato_mash": 200, "potato": 220}), C({"milk": 40}), C({"butter": 15}), C({"lingonberry": 30}), C({"onion": 15}, False)]),
 dict(id="green_curry", split="heldout", name="Thai green curry with chicken and jasmine rice", fi="Vihreä thaicurry ja kana", diet=[], components=[
   C({"chicken_fillet": 130, "chicken_thigh": 130, "chicken_any": 130}), C({"coconut_milk": 100}), C({"curry_powder": 10}), C({"bell_pepper": 40}, False),
   C({"rice": 75})]),
 dict(id="vegan_bolognese", split="heldout", name="Vegan fava-bean bolognese with pasta", fi="Härkis-bolognese (vegaaninen)", diet=["vegan"], components=[
   C({"plant_mince": 100}), C({"pasta": 100, "spaghetti": 100}), C({"tomato_canned": 100}), C({"onion": 30}), C({"garlic": 3}, False)]),
 dict(id="greek_salad", split="heldout", name="Greek salad", fi="Kreikkalainen salaatti", diet=["vegetarian"], components=[
   C({"tomato_fresh": 80}), C({"cucumber": 60}), C({"feta": 40}), C({"olives": 15}), C({"red_onion": 15, "onion": 15}, False), C({"lettuce": 30}, False), C({"oil": 10}, False)]),
 dict(id="tomato_soup", split="heldout", name="Tomato soup with basil (vegan)", fi="Tomaattikeitto (vegaaninen)", diet=["vegan"], components=[
   C({"tomato_canned": 200}), C({"onion": 30}), C({"garlic": 3}, False), C({"veg_stock": 10}), C({"basil": 1}, False)]),
 dict(id="pork_mushroom", split="heldout", name="Pork tenderloin with creamy mushroom sauce and potatoes", fi="Porsaan sisäfilee, sienikastike ja perunat", diet=[], components=[
   C({"pork_fillet": 160}, subs={"pork_stew_cut": 170, "chicken_fillet": 160, "turkey": 160}), C({"mushroom": 60}), C({"cream": 60, "whipping_cream": 50}), C({"onion": 15}, False), C({"potato": 200})]),
 dict(id="omelette", split="heldout", name="Ham and cheese omelette (breakfast)", fi="Kinkku-juustomunakas", diet=[], components=[
   C({"egg": 120}), C({"ham": 30}), C({"hard_cheese": 20}), C({"milk": 20}, False)]),
 dict(id="salmon_sandwich", split="heldout", name="Smoked salmon and cream cheese sandwich", fi="Savulohileipä", diet=[], components=[
   C({"bread_roll": 80}), C({"smoked_salmon": 50}), C({"cream_cheese": 25}), C({"cucumber": 15, "lettuce": 15}), C({"red_onion": 5}, False)]),
 dict(id="halloumi_salad", split="heldout", name="Grilled halloumi salad", fi="Halloumisalaatti", diet=["vegetarian"], components=[
   C({"halloumi": 80}, subs={"bread_cheese": 80, "feta": 60}), C({"lettuce": 50}), C({"tomato_fresh": 40}), C({"cucumber": 30}), C({"oil": 10}, False)]),
 dict(id="stroganoff", split="heldout", name="Beef stroganoff with rice", fi="Boeuf stroganoff ja riisi", diet=[], components=[
   C({"beef_steak": 130, "beef_stew_cut": 130}), C({"onion": 30}), C({"sour_cream": 50, "cream": 50}), C({"pickled_cucumber": 15}, False),
   C({"tomato_paste": 10}, False), C({"rice": 75, "potato_mash": 200})]),
 dict(id="caesar_wrap", split="heldout", name="Chicken Caesar wrap", fi="Kana-caesar-wrap", diet=[], components=[
   C({"tortilla": 60}), C({"chicken_any": 80, "chicken_fillet": 80}), C({"romaine": 30, "lettuce": 30}), C({"caesar_dressing": 20, "mayonnaise": 20}), C({"parmesan": 5}, False)]),
 dict(id="fish_chips", split="heldout", name="Fish and chips", fi="Fish and chips", diet=[], components=[
   C({"white_fish": 150}), C({"flour": 20}), C({"fries": 200, "potato": 220}), C({"lemon": 5}, False), C({"mayonnaise": 20}, False)]),
 dict(id="berry_pie", split="heldout", name="Blueberry pie with vanilla sauce", fi="Mustikkapiirakka ja vaniljakastike", diet=["vegetarian"], components=[
   C({"flour": 40}), C({"butter": 25}), C({"sugar": 20}), C({"egg": 15}), C({"berries_frozen": 50}), C({"sour_cream": 30, "quark": 30}, False),
   C({"vanilla_sauce": 40}, False)]),
]
DISHES = [d for d in DISHES if not d.get("disabled")]
BY_ID = {d["id"]: d for d in DISHES}
