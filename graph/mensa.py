"""Canteen-menu questions: recognised, read and answered from the
Studierendenwerk's own menu data (ingestion/mensa.py), never from a model's
idea of what a canteen serves.

Everything that decides which meals an answer is about is plain code -
which day ("today", "morgen", "on Friday"), which canteen, which diet or
allergen the student wants to avoid - so the answer model only puts the
selected meals into words, and the interface shows the same meals as cards
with their photos. Prices, codes and dishes therefore come from the menu
and nowhere else.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from langchain_core.documents import Document

from ingestion import mensa

logger = logging.getLogger(__name__)

# A question about what the canteens serve. Not about their opening hours
# or the 2026 price increase: the documents answer those.
_MENU_CUE = re.compile(
    r"\b(mensa|mensen|canteen|cafeteria|speiseplan|men(u|ü)s?|lunch|mittag(essen)?|"
    r"what('?s| is) (there )?(to eat|for (lunch|dinner|food))|was gibt es (heute |morgen )?(zu essen|in der mensa)|"
    r"essen (heute|morgen)|(today|tomorrow)'?s? (food|meals?|dishes)|gericht(e)?|dish(es)? (today|tomorrow))\b",
    re.I,
)
_FOOD_WORDS = re.compile(r"\b(eat|food|meal|meals|dish|dishes|vegan|vegetarian|vegetarisch|essen|gericht)\b", re.I)
_NOT_MENU = re.compile(
    r"open(ing)?\b|hours|öffnungszeit|geöffnet|price (increase|rise|change)|prices? (go|went|will) up|"
    r"teurer|preiserhöhung|2026 (price|rent)|job|arbeit(en)? in der mensa|work (in|at) the (mensa|canteen)",
    re.I,
)

_WEEKDAYS = {
    0: ("monday", "montag"), 1: ("tuesday", "dienstag"), 2: ("wednesday", "mittwoch"),
    3: ("thursday", "donnerstag"), 4: ("friday", "freitag"), 5: ("saturday", "samstag"), 6: ("sunday", "sonntag"),
}

# Diet wishes: (pattern, pictograms a meal must have one of, pictograms it must not have, codes it must not have)
_INCLUDE = [
    (re.compile(r"\bvegan", re.I), {"V+"}, set(), set()),
    (re.compile(r"\bvegetari|\bvegetarisch|without meat|no meat|ohne fleisch|fleischlos|meat[- ]free", re.I), {"V", "V+"}, set(), set()),
    (re.compile(r"\bfish\b|\bfisch\b", re.I), {"F"}, set(), set()),
    (re.compile(r"\bchicken|\bpoultry|\bgeflügel|\bhähnchen|\bhuhn", re.I), {"G"}, set(), set()),
    (re.compile(r"\bbeef\b|\brind", re.I), {"R"}, set(), set()),
]
_PORK = re.compile(r"no pork|without pork|pork[- ]free|ohne schwein|kein schwein|halal", re.I)
_HALAL = re.compile(r"halal", re.I)
_GLUTEN = {"Di", "Ge", "Ha", "Hy", "Ka", "Ro", "We"}
# Codes as the menu's legend lists them (checked 2026-10-15).
_NUTS = {"Cn", "Hn", "Ma", "Mn", "Pa", "Pi", "Pn", "Wa"}
# Allergen wishes: pattern -> codes a meal must not carry.
_EXCLUDE = [
    (re.compile(r"gluten|glutenfrei|coeliac|celiac|zöliakie", re.I), _GLUTEN),
    (re.compile(r"lactose|laktose|dairy|milk[- ]free|without milk|no milk|ohne milch|milchfrei", re.I), {"Mi"}),
    (re.compile(r"\bnuts?\b|nut[- ]free|nussfrei|ohne nüsse|nut allerg", re.I), _NUTS | {"En"}),
    (re.compile(r"peanut|erdnuss", re.I), {"En"}),
    (re.compile(r"\beggs?\b|egg[- ]free|ohne ei\b|eifrei", re.I), {"Ei"}),
    (re.compile(r"\bsoy|\bsoja", re.I), {"So"}),
    (re.compile(r"sesame|sesam", re.I), {"Se"}),
    (re.compile(r"shellfish|crustacean|seafood|krebstier|meeresfrücht|weichtier|mollus", re.I), {"Kr", "Wt"}),
    (re.compile(r"celery|sellerie", re.I), {"Sl"}),
    (re.compile(r"mustard|senf", re.I), {"Sf"}),
    (re.compile(r"alcohol|alkohol|halal", re.I), {"A"}),
    (re.compile(r"garlic|knoblauch", re.I), {"Kn"}),
]
_ABOUT_SIDES = re.compile(r"soup|side|salad|dessert|suppe|beilage|salat|nachtisch|nachspeise", re.I)
_ALLERGEN_CONTEXT = re.compile(r"allerg|free|frei|without|ohne|no\b|kein|intoleran|unverträglich|avoid|can'?t eat|cannot eat", re.I)


@dataclass
class MenuRequest:
    day: date
    locations: list[int]
    lang: str
    must_have: list[set[str]] = field(default_factory=list)  # each: one of these pictograms
    no_pictograms: set[str] = field(default_factory=set)
    no_codes: set[str] = field(default_factory=set)
    halal: bool = False
    wishes: list[str] = field(default_factory=list)  # what was asked for, for the answer text


def is_menu_question(question: str) -> bool:
    if _NOT_MENU.search(question):
        return False
    if _MENU_CUE.search(question):
        return True
    # "Is there something vegan today?" names no canteen but means its menu.
    return bool(_FOOD_WORDS.search(question) and re.search(r"\b(today|tomorrow|heute|morgen)\b", question, re.I))


def _requested_day(question: str, today: date) -> date:
    q = question.casefold()
    if re.search(r"day after tomorrow|übermorgen", q):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b|\bmorgen\b", q):
        return today + timedelta(days=1)
    next_week = bool(re.search(r"next week|nächste woche|naechste woche", q))
    for weekday, names in _WEEKDAYS.items():
        if any(re.search(rf"\b{n}s?\b", q) for n in names):
            ahead = (weekday - today.weekday()) % 7
            if next_week and ahead < 7 - today.weekday():
                ahead += 7
            return today + timedelta(days=ahead)
    return today


def parse_request(question: str, today: date, lang: str) -> MenuRequest:
    q = question.casefold()
    locations = []
    if "wechloy" in q:
        locations.append(3)
    if re.search(r"uhlhorn|haarentor", q):
        locations.append(2)
    if re.search(r"both|all (the )?(canteens|mensas)|beide|alle mensen", q):
        locations = [2, 3]
    request = MenuRequest(day=_requested_day(question, today), locations=locations or [mensa.DEFAULT_LOCATION], lang=lang)
    for pattern, must, _no_pict, _no_codes in _INCLUDE:
        if pattern.search(question):
            request.must_have.append(must)
            request.wishes.append(pattern.search(question).group(0))
    if _PORK.search(question):
        request.no_pictograms |= {"S"}
        request.no_codes |= {"SG"}
        request.wishes.append("no pork")
    if _HALAL.search(question):
        # The menu does not mark halal; the most it can say is no pork, no
        # pork gelatine and no alcohol.
        request.halal = True
        request.no_codes |= {"A"}
    if _ALLERGEN_CONTEXT.search(question):
        for pattern, codes in _EXCLUDE:
            match = pattern.search(question)
            if match:
                request.no_codes |= codes
                request.wishes.append(f"without {match.group(0)}")
    return request


def matches(meal: mensa.Meal, request: MenuRequest) -> bool:
    if any(not (set(meal.pictograms) & must) for must in request.must_have):
        return False
    if set(meal.pictograms) & request.no_pictograms:
        return False
    return not (set(meal.codes) & request.no_codes)


def _filtered(meals: list[mensa.Meal], request: MenuRequest) -> list[mensa.Meal]:
    return [m for m in meals if matches(m, request)]


def _next_day_with_menu(location: int, start: date, lang: str) -> tuple[date, list, list] | None:
    for offset in range(1, 8):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        meals, notes = mensa.get_menu(location, day, lang)
        if meals:
            return day, meals, notes
    return None


def _describe(meal: mensa.Meal, legend: mensa.Legend) -> str:
    prices = meal.prices
    price = (
        f"students {prices.get('students', '?')} EUR, employees {prices.get('employees', '?')} EUR, "
        f"guests {prices.get('guests', '?')} EUR"
        if prices else "price not given"
    )
    diet = ", ".join(legend.pictograms.get(p, {}).get("label", p) for p in meal.pictograms) or "no diet marking"
    allergens = [legend.labels[c] for c in meal.codes if legend.kinds.get(c) == "allergen" and c in legend.labels]
    additives = [legend.labels[c] for c in meal.codes if legend.kinds.get(c) == "additive" and c in legend.labels]
    notes = [legend.labels[c] for c in meal.codes if legend.kinds.get(c) == "note" and c in legend.labels]
    parts = [f"- {meal.name} ({meal.counter.title() if meal.counter else 'main counter'}): {price}; {diet}"]
    if allergens:
        parts.append(f"allergens: {', '.join(allergens)}")
    if additives:
        parts.append(f"additives: {', '.join(additives)}")
    if notes:
        parts.append(", ".join(notes))
    return "; ".join(parts)


def answer_material(question: str, today: date, lang: str) -> tuple[list[Document], dict | None]:
    """The menu passage for the answer model, and the payload for the
    interface's cards. On any failure to load the menu, a passage saying so
    and pointing to the official page, and no cards."""
    request = parse_request(question, today, lang)
    try:
        legend = mensa.get_legend(lang)
    except Exception:  # noqa: BLE001 - the answer says the menu could not be loaded
        logger.warning("Could not load the canteen legend", exc_info=True)
        legend = None

    lines, payloads = [], []
    for location in request.locations:
        name = mensa.LOCATIONS[location]["name"]
        official = mensa.OFFICIAL_PAGE.format(location=location, lang=lang)
        try:
            meals, notes = mensa.get_menu(location, request.day, lang) if legend else ([], [])
            if legend is None:
                raise RuntimeError("legend unavailable")
        except Exception:  # noqa: BLE001
            logger.warning("Could not load the menu of %s for %s", name, request.day, exc_info=True)
            lines.append(f"The menu of {name} could not be loaded right now. The official menu: {official}")
            continue

        day = request.day
        header = f"Official menu of {name} for {day.strftime('%A, %d %B %Y')} (from the Studierendenwerk Oldenburg)."
        if not meals:
            nxt = _next_day_with_menu(location, day, lang)
            if nxt is None:
                lines.append(f"{name} has no menu for {day.strftime('%A, %d %B %Y')} or the following days. Official menu: {official}")
                continue
            lines.append(f"{name} has no menu for {day.strftime('%A, %d %B %Y')} (closed that day).")
            day, meals, notes = nxt
            header = f"The next menu of {name} is for {day.strftime('%A, %d %B %Y')}."

        chosen = _filtered(meals, request)
        mains = [m for m in chosen if not m.side]
        sides = [m for m in chosen if m.side]
        lines.append(header)
        if request.wishes:
            lines.append(f"The student asked for: {', '.join(dict.fromkeys(request.wishes))}. Only dishes meeting that are listed below.")
        if not chosen:
            lines.append(f"No dish on this menu meets that ({len(meals)} dishes in total).")
        if mains:
            lines.append("Main dishes:")
            lines += [_describe(m, legend) for m in mains]
        if sides and _ABOUT_SIDES.search(question):
            lines.append("Soups, side dishes, salads and desserts:")
            lines += [_describe(m, legend) for m in sides]
        elif sides:
            # Details are on the cards; listing them all made the answer a
            # copy of the cards.
            lines.append(
                f"Also {len(sides)} soups, side dishes, salads and desserts: {', '.join(m.name for m in sides)}."
            )
        lines += notes
        if request.no_codes - {"A", "Kn", "SG"}:
            lines.append(
                "Chosen by the menu's allergen codes only. The menu does not cover traces or cross-contact "
                "in the kitchen: anyone with a severe allergy should ask the canteen staff."
            )
        if request.halal:
            lines.append(
                "The menu does not mark dishes as halal. The dishes listed carry no pork, pork gelatine or "
                "alcohol according to the menu's codes; that is all the menu says."
            )
        lines.append(f"Official menu page: {official}")
        payloads.append(mensa.menu_payload(location, day, chosen, legend, lang, notes))

    text = "\n".join(lines)
    note = (
        "How to answer: the student also sees every dish below as a card with its photo, all prices, "
        "allergens and additives. So answer briefly: say which canteen and day, and name the main dishes "
        "that fit what was asked with their student price. Mention soups, sides, salads and desserts in at "
        "most one sentence. Name allergens or additives only if the question is about them; if the passage "
        "says the selection follows the allergen codes only, say so. Never add a dish, price or ingredient "
        "that is not listed."
    )
    doc = Document(
        page_content=text,
        metadata={
            "source_id": "mensa_menu",
            "source_url": mensa.OFFICIAL_PAGE.format(location=request.locations[0], lang=lang),
            "title": "Canteen menu (Studierendenwerk Oldenburg)",
            "model_note": note,
        },
    )
    payload = {"menus": payloads, "wishes": list(dict.fromkeys(request.wishes))} if payloads else None
    return [doc], payload
