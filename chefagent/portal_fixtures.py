"""Hotel Aurora account records. Recipe amounts and stock are kitchen-owned data.
Prices, availability, cut-offs and product names are never authored here.
"""

import copy
from . import kitchen_fixtures as legacy

KITCHEN = copy.deepcopy(legacy.KITCHEN)
KITCHEN["budget"] = 1500
INGREDIENTS = copy.deepcopy(legacy.INGREDIENTS)
INGREDIENTS.update(
    {
        "bread": {"ids": ["472236"], "unit": "kg"},
        "yogurt": {"ids": ["464517"], "unit": "kg"},
        "coffee": {"ids": ["462090"], "unit": "kg"},
        "tea": {"ids": ["471426"], "unit": "kg"},
        "orange": {"ids": ["465262"], "unit": "l"},
        "cucumber": {"ids": ["475568"], "unit": "kg"},
        "tomato_juice": {"ids": ["463205"], "unit": "l"},
    }
)
STOCK = copy.deepcopy(legacy.STOCK)
STOCK["dill"] = 2
STOCK.update(
    dict.fromkeys(
        ["bread", "yogurt", "coffee", "tea", "orange", "cucumber", "tomato_juice"], 0
    )
)
RECIPES = copy.deepcopy(legacy.RECIPES)
RECIPES["breakfast"]["ingredients"].update(
    {
        "bread": 60,
        "yogurt": 100,
        "coffee": 10,
        "tea": 0.5,
        "orange": 150,
        "cucumber": 25,
        "tomato_juice": 50,
    }
)
RECIPES["staff_porridge"]["ingredients"]["cream"] = 30
RECIPES["soup"]["name"] = "Salmon soup"
RECIPES["whitefish"]["name"] = "Whitefish with potatoes"
DELIVERIES = legacy.DELIVERIES
BASE_SERVICES = legacy.BASE_SERVICES
TEAM = [
    {"name": "Sanna Virtanen", "role": "Head chef", "permission": "Can place orders"},
    {"name": "Mikko Lahti", "role": "Sous chef", "permission": "Can prepare orders"},
    {
        "name": "Aurora Group assistant",
        "role": "Connected assistants",
        "permission": "Can place orders",
    },
]
RULES = {
    "weekly_limit": 1500,
    "over_limit": "ask",
    "ask_swap": True,
    "same_allergens": True,
    "allergens": ["nuts", "peanuts"],
    "growth_limit": 200,
    "monthly_limit": 6000,
    "changed_at": "2026-11-02",
    "changed_by": "Sanna",
    "version": 1,
}
# Historical account invoices contain product quantities, not invented prices.
# Their totals are computed from the same customer price source, visibly dated.
HISTORY = [
    {"id": "AU-10481", "by": "Sanna Virtanen", "date": "2026-11-13", "factor": 1},
    {"id": "AU-10480", "by": "Mikko Lahti", "date": "2026-11-09", "factor": 0.9},
    {"id": "AU-10479", "by": "Sanna Virtanen", "date": "2026-11-06", "factor": 1.1},
    {"id": "AU-10478", "by": "Mikko Lahti", "date": "2026-11-02", "factor": 0.85},
    {"id": "AU-10477", "by": "Sanna Virtanen", "date": "2026-10-30", "factor": 1},
]
