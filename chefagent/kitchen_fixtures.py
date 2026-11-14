"""Authored demo kitchen, not Valio stock. Amounts kg/l; recipes g/ml per cover.
Product identifiers refer to the sponsor catalogue. No prices are fixtures.
"""
KITCHEN = {
    'name': 'Hotel Aurora', 'location': 'Helsinki', 'customer': 'HC-1001',
    'budget': 800, 'week': 'Week 47 · 16–22 Nov',
    'policy': {'free_from': ['nuts', 'peanuts'], 'strict_may_contain': True},
    'rules': ['No nuts or peanuts, including may contain.',
              'A recipe swap may add no allergens and must keep the cooking method.',
              'Chef approval for every recipe swap and larger pack.',
              'Weekly budget needs a new approval whenever its order changes.',
              'Opened cream is used within 48 hours. Buy only against booked recipes.'],
    'bookings': [
        {'day': 'Mon', 'date': '2026-11-16', 'covers': 80},
        {'day': 'Tue', 'date': '2026-11-17', 'covers': 56},
        {'day': 'Wed', 'date': '2026-11-18', 'covers': 72},
        {'day': 'Thu', 'date': '2026-11-19', 'covers': 64},
        {'day': 'Fri', 'date': '2026-11-20', 'covers': 60},
        {'day': 'Sat', 'date': '2026-11-21', 'covers': 44},
        {'day': 'Sun', 'date': '2026-11-22', 'covers': 36},
    ],
    'fixture_note': 'Demo kitchen: authored menus, recipes, bookings, stock and handling rules. Prices and supply are from Valio.',
}
# Each role has an intentionally narrow, recipe-specific catalogue shortlist.
INGREDIENTS = {
    'fish': {'ids': ['461907', '461883'], 'unit': 'kg'},
    'whitefish': {'ids': ['469335'], 'unit': 'kg'},
    'potato': {'ids': ['471970'], 'unit': 'kg'},
    'carrot': {'ids': ['475454'], 'unit': 'kg'},
    'onion': {'ids': ['475561'], 'unit': 'kg'},
    'cream': {'ids': ['464699', '465193'], 'unit': 'l'},
    'butter': {'ids': ['463437'], 'unit': 'kg'},
    'milk': {'ids': ['464119'], 'unit': 'l'},
    'oats': {'ids': ['460200'], 'unit': 'kg'},
    'egg': {'ids': ['463883'], 'unit': 'kg'},
    'cheese': {'ids': ['474963'], 'unit': 'kg'},
    'flour': {'ids': ['476417'], 'unit': 'kg'},
    'sugar': {'ids': ['460325'], 'unit': 'kg'},
    'lemon': {'ids': ['469312'], 'unit': 'l'},
    'dill': {'ids': ['471954'], 'unit': 'kg'},
}
STOCK = {'fish': 21, 'potato': 8, 'carrot': 3, 'onion': 1,
         'cream': 1, 'butter': 1, 'milk': 8, 'oats': 2,
         'egg': 2, 'cheese': 1, 'flour': 0, 'sugar': 0, 'lemon': 0, 'dill': .4,
         'whitefish': 0}
# All existing fish is frozen, reserved chronologically for the weekly soup.
RECIPES = {
    'breakfast': {'name': 'Breakfast', 'ingredients': {'oats': 45, 'milk': 180, 'egg': 90, 'cheese': 25, 'butter': 12}},
    'staff_porridge': {'name': 'Staff breakfast porridge', 'ingredients': {'oats': 45, 'cream': 35}},
    'soup': {'name': 'Lohikeitto', 'ingredients': {'fish': 150, 'potato': 180, 'carrot': 60, 'onion': 25, 'cream': 60, 'dill': 3}},
    'vegetables': {'name': 'Roasted vegetables', 'ingredients': {'potato': 200, 'carrot': 150, 'onion': 35, 'cream': 60, 'butter': 15}},
    'salmon': {'name': 'Salmon with dill potatoes', 'ingredients': {'fish': 150, 'potato': 180, 'carrot': 80, 'cream': 45, 'butter': 15, 'dill': 3, 'lemon': 10}},
    'tart': {'name': 'Lemon tart', 'ingredients': {'flour': 40, 'butter': 25, 'sugar': 35, 'egg': 35, 'lemon': 30, 'cream': 30}},
    'whitefish': {'name': 'Paistettu siika', 'ingredients': {'whitefish': 150, 'potato': 180, 'carrot': 80, 'cream': 45, 'butter': 15, 'dill': 3, 'lemon': 10}},
    'cheeseboard': {'name': 'Juustolautanen', 'ingredients': {'cheese': 80}},
}
DELIVERIES = ['2026-11-16', '2026-11-18', '2026-11-20']
BASE_SERVICES = [
    *[{'date': b['date'], 'recipe': 'breakfast', 'covers': b['covers']} for b in KITCHEN['bookings']],
    {'date': '2026-11-16', 'recipe': 'soup', 'covers': 80},
    {'date': '2026-11-18', 'recipe': 'vegetables', 'covers': 72},
    {'date': '2026-11-20', 'recipe': 'soup', 'covers': 60},
    {'date': '2026-11-22', 'recipe': 'staff_porridge', 'covers': 40},
]
WEDDING_TEXT = 'Wedding Saturday, 120 guests, salmon and lemon tart'
# An explicit final menu, so the photo never needs to infer what crossed-out text means.
BOARD_TEXT = 'Saturday wedding, 120 guests. Final menu: Paistettu siika 120, Lemon tart 120, Juustolautanen 140. No Lohikeitto.'
