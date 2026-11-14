"""Request intake: free text (a menu, a direct product request, or both) -> structured services."""
from chefagent import llm

PARSE_PROMPT = """A hotel kitchen sent a purchasing request: a menu for next week, a direct product request
(e.g. "1,000 litres of lactose-free milk by Monday"), or both. Convert it to JSON.
Today is Saturday 2026-11-14; "Monday" means 2026-11-16, etc. If no covers are given for a line,
use the nearest covers mentioned for that meal, else 100.
Text:
---
{text}
---
Return {{"services": [{{"date": "YYYY-MM-DD", "meal": short label,
  "items": [ either a dish: {{"text": the menu line as written, "covers": int, "diet": subset of ["vegan","vegetarian","gluten-free","milk-free"]}}
             or a direct product request: {{"text": the request as written, "direct": true, "ingredient": what to buy incl. requirements (e.g. "lactose-free milk"),
               "search": [3-5 English+Finnish catalogue search phrases], "qty": number, "unit": "kg"|"l", "covers": 1, "diet": []}} ]}}]}}
For a direct request, "date" is the date the goods must arrive (e.g. "by Monday" = 2026-11-16) and meal is "Delivery"."""


def parse_request(text: str) -> dict:
    return llm.ask_json(PARSE_PROMPT.format(text=(text or "")[:4000]))
