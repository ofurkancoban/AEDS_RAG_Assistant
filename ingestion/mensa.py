"""The Studierendenwerk Oldenburg's canteen (Mensa) menus, as data.

The menus are not documents to search: they change every day, carry
photos, prices and allergen codes, and a model must never make up a dish.
So they are fetched from the Studierendenwerk's own menu system
(sw-oldenburg-spl56.maxmanager.xyz, the page its website embeds), parsed
into meals, and handed to the answer model only to put into words - the
same meals go to the interface as cards with their photos.

The page loads a day's menu with one POST (inc/ajax-php_konnektor.inc.php,
func=make_spl), as its own project.js does; the legend (what "Mi", "(4)"
and the pictograms mean) is read from the page itself, so a code the
Studierendenwerk adds or renames is picked up without a change here.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

BASE_URL = "https://sw-oldenburg-spl56.maxmanager.xyz"
# The two canteens on the Oldenburg campuses; the system also serves
# Elsfleth (5), Wilhelmshaven (6) and Emden (7), which are not where this
# programme's students study. Ids from the Studierendenwerk's canteen pages.
LOCATIONS = {
    2: {"name": "Mensa Uhlhornsweg", "slug": "uhlhornsweg"},
    3: {"name": "Mensa Wechloy", "slug": "wechloy"},
}
DEFAULT_LOCATION = 2
OFFICIAL_PAGE = BASE_URL + "/index.php?locationId={location}&lang={lang}"

# Counters whose dishes are sides rather than meals of their own.
_SIDE_GROUPS = re.compile(r"soup|side dish|salad|dessert|beilage|salat|suppe|nachtisch|nachspeise", re.I)

_CACHE_TTL_S = 30 * 60
_cache: dict[tuple, tuple[float, object]] = {}
_cache_lock = threading.Lock()


@dataclass
class Meal:
    name: str
    counter: str
    codes: list[str]
    prices: dict[str, str]  # students / employees / guests, as printed ("2,50")
    pictograms: list[str]  # pictogram codes ("V", "V+", "S"...)
    image: str | None  # path on the menu server ("assets/fotos/..."), None for a placeholder
    side: bool = False


@dataclass
class Legend:
    pictograms: dict[str, dict] = field(default_factory=dict)  # code -> {label, icon}
    labels: dict[str, str] = field(default_factory=dict)  # code -> label, every other code
    kinds: dict[str, str] = field(default_factory=dict)  # code -> allergen / additive / note


def _post_menu(location: int, day: date, lang: str) -> str:
    import httpx

    monday = day - timedelta(days=day.weekday())
    response = httpx.post(
        f"{BASE_URL}/inc/ajax-php_konnektor.inc.php",
        data={
            "func": "make_spl",
            "locId": location,
            "date": day.isoformat(),
            "lang": lang,
            "startThisWeek": monday.isoformat(),
            "startNextWeek": (monday + timedelta(days=7)).isoformat(),
        },
        headers={"User-Agent": "AEDS-RAG-Assistant (University of Oldenburg study assistant)"},
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_menu(fragment: str) -> list[Meal]:
    """Meals from the menu HTML the POST returns, in page order."""
    meals: list[Meal] = []
    counter = ""
    # The fragment alternates counter headers and meal rows; walk both in order.
    for match in re.finditer(
        r"<div class='col-xs-4 gruppenname'>(?P<group>.*?)</div>|<div class='row splMeal' lang='(?P<codes>[^']*)'>(?P<body>.*?)(?=<div class='row (?:splMeal|gruppenkopf)|\Z)",
        fragment,
        re.S,
    ):
        if match.group("group") is not None:
            counter = _text(match.group("group"))
            continue
        body = match.group("body")
        name_match = re.search(r"font-size:24px'>(.*?)<div class='kennz'>", body, re.S) or re.search(
            r"font-size:24px'>(.*?)</span>", body, re.S
        )
        if not name_match:
            continue
        price_match = re.search(r"<div class='preise'><span>(.*?)</span>", body, re.S)
        prices = [p.strip() for p in _text(price_match.group(1)).replace("€", "").split("/")] if price_match else []
        image_match = re.search(r"src='(assets/fotos/[^'?]+)", body)
        image = image_match.group(1) if image_match and "/dummies/" not in image_match.group(1) else None
        pictograms = list(dict.fromkeys(re.findall(r"assets/icons/([^'\"]+?)\.png'[^>]*class='iconLarge'", body)))
        codes = [c for c in (html.unescape(c).strip() for c in match.group("codes").split(",")) if re.fullmatch(r"[\w+]+", c)]
        meals.append(
            Meal(
                name=_text(name_match.group(1)),
                counter=counter,
                codes=[c for c in codes if c not in pictograms],
                prices=dict(zip(("students", "employees", "guests"), prices)),
                pictograms=pictograms,
                image=image,
                side=bool(_SIDE_GROUPS.search(counter)),
            )
        )
    return meals


def parse_notes(fragment: str) -> list[str]:
    """Footnotes printed under a day's menu ("* Menu price max. 2,50 EUR
    includes two side dishes...")."""
    notes = re.findall(r">\s*(\*\s*[^<>]{10,300}?)\s*<", fragment)
    return list(dict.fromkeys(_text(n) for n in notes))


def parse_legend(page: str) -> Legend:
    """The page's legend: pictogram icons with their meaning, and every code
    ("Mi", "We", "(4)", "Kn"...) with its label and kind."""
    legend = Legend()
    start = page.find("LEGEND</h4>")
    section = page[start:] if start >= 0 else page
    kind = "note"
    for row in re.finditer(r"<tr>(.*?)</tr>", section, re.S):
        th = re.search(r"<th[^>]*>(.*?)</th>", row.group(1), re.S)
        if th:
            heading = _text(th.group(1)).lower()
            kind = (
                "pictogram" if "pictogram" in heading or "piktogramm" in heading
                else "additive" if "additive" in heading or "zusatz" in heading
                else "allergen" if "allergen" in heading
                else kind
            )
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(1), re.S)
        if len(cells) != 2:
            continue
        icon = re.search(r"assets/icons/([^\"']+?)\.png", cells[0])
        label = _text(cells[1])
        if icon:
            legend.pictograms[icon.group(1)] = {"label": label, "icon": f"assets/icons/{icon.group(1)}.png"}
            continue
        code = _text(cells[0]).strip("()")
        if code and label:
            legend.labels[code] = label
            # Codes listed under PICTOGRAMS but without an icon ("A" alcohol,
            # "Kn" garlic, gelatine) are notes, not allergens or additives.
            legend.kinds[code] = "note" if kind == "pictogram" else kind
    return legend


def _cached(key: tuple, load, force: bool = False):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_S and not force:
            return hit[1]
    value = load()
    with _cache_lock:
        _cache[key] = (now, value)
    return value


def get_legend(lang: str = "en", force: bool = False) -> Legend:
    import httpx

    def load():
        page = httpx.get(
            OFFICIAL_PAGE.format(location=DEFAULT_LOCATION, lang=lang),
            headers={"User-Agent": "AEDS-RAG-Assistant (University of Oldenburg study assistant)"},
            timeout=15,
        )
        page.raise_for_status()
        return parse_legend(page.text)

    return _cached(("legend", lang), load, force)


def get_menu(location: int, day: date, lang: str = "en", force: bool = False) -> tuple[list[Meal], list[str]]:
    """A day's meals at one canteen, and the footnotes under them."""

    def load():
        fragment = _post_menu(location, day, lang)
        return parse_menu(fragment), parse_notes(fragment)

    return _cached(("menu", location, day.isoformat(), lang), load, force)


# Lunch-time window (Berlin) in which today's menus are kept loaded, so a
# student's menu question does not wait for the menu server (one to three
# seconds per canteen, more when it is slow). Refreshed more often than the
# cache expires, so the cache is never cold inside the window.
PREFETCH_HOURS = (6, 15)
PREFETCH_EVERY_S = 20 * 60


def prefetch(day: date) -> int:
    """Loads `day`'s menus (both canteens, English and German), the legends
    and every dish photo and diet icon into the caches. Returns the number
    of meals seen."""
    from api.routes_mensa import ImageUnavailable, cached_image

    meals_seen = 0
    for lang in ("en", "de"):
        try:
            get_legend(lang, force=True)
        except Exception:  # noqa: BLE001 - a prefetch failure only means a slower first question
            logger.warning("Menu prefetch: legend (%s) failed", lang, exc_info=True)
        for location in LOCATIONS:
            try:
                meals, _ = get_menu(location, day, lang, force=True)
            except Exception:  # noqa: BLE001
                logger.warning("Menu prefetch: location %s (%s) failed", location, lang, exc_info=True)
                continue
            meals_seen += len(meals)
            if lang != "en":
                continue  # same photos in both languages
            for meal in meals:
                for src in ([meal.image] if meal.image else []) + [f"assets/icons/{p}.png" for p in meal.pictograms]:
                    try:
                        cached_image(src)
                    except ImageUnavailable:
                        pass
    return meals_seen


def start_prefetch() -> None:
    """Background thread for the API process (the menu cache lives in its
    memory, so a cron job could not warm it)."""
    from zoneinfo import ZoneInfo

    def loop():
        while True:
            now = datetime.now(ZoneInfo("Europe/Berlin"))
            if now.weekday() < 5 and PREFETCH_HOURS[0] <= now.hour < PREFETCH_HOURS[1]:
                try:
                    prefetch(now.date())
                except Exception:  # noqa: BLE001
                    logger.warning("Menu prefetch failed", exc_info=True)
            time.sleep(PREFETCH_EVERY_S)

    threading.Thread(target=loop, name="mensa-prefetch", daemon=True).start()


def menu_payload(location: int, day: date, meals: list[Meal], legend: Legend, lang: str, notes: list[str] = ()) -> dict:
    """What the interface gets: the meals with their codes spelled out, and
    the legend entries those meals use."""
    used = sorted({c for m in meals for c in m.codes if c in legend.labels})
    used_pictograms = sorted({p for m in meals for p in m.pictograms})
    return {
        "location": LOCATIONS[location]["name"],
        "date": day.isoformat(),
        "official_url": OFFICIAL_PAGE.format(location=location, lang=lang),
        "notes": list(notes),
        "meals": [
            {
                **asdict(m),
                # Only codes the legend explains ("NM" is printed on the menu
                # but never explained, so no label is made up for it).
                "labels": [
                    {"code": c, "label": legend.labels[c], "kind": legend.kinds.get(c, "note")}
                    for c in m.codes
                    if c in legend.labels
                ],
                "pictogram_labels": [
                    {"code": p, "label": legend.pictograms.get(p, {}).get("label", p), "icon": f"assets/icons/{p}.png"}
                    for p in m.pictograms
                ],
            }
            for m in meals
        ],
        "legend": {
            "codes": [{"code": c, "label": legend.labels[c], "kind": legend.kinds.get(c, "note")} for c in used],
            "pictograms": [
                {"code": p, "label": legend.pictograms.get(p, {}).get("label", p), "icon": f"assets/icons/{p}.png"}
                for p in used_pictograms
            ],
        },
    }
