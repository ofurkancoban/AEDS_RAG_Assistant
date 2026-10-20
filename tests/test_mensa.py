"""Canteen menus: parsing the Studierendenwerk's menu and legend (saved real
pages, no network), reading a menu question, choosing the meals, and the
photo proxy."""

from datetime import date
from pathlib import Path

import httpx
import pytest

from graph import mensa as menu_q
from ingestion import mensa

FIXTURES = Path(__file__).parent / "fixtures"
THURSDAY = date(2026, 10, 15)


@pytest.fixture
def menu():
    return mensa.parse_menu((FIXTURES / "mensa_menu_2026-10-15.html").read_text(encoding="utf-8"))


@pytest.fixture
def legend():
    return mensa.parse_legend((FIXTURES / "mensa_legend.html").read_text(encoding="utf-8"))


@pytest.fixture
def offline(monkeypatch, menu, legend):
    """get_menu / get_legend from the saved pages: Thursday has a menu,
    the weekend none, Monday the same menu again."""
    monkeypatch.setattr(mensa, "get_legend", lambda lang="en": legend)

    def get_menu(location, day, lang="en"):
        return ([], []) if day.weekday() >= 5 else (menu, ["* Menu price max. 2,50 EUR includes two side dishes."])

    monkeypatch.setattr(mensa, "get_menu", get_menu)


def test_meals_are_parsed_with_counter_prices_codes_and_photo(menu):
    assert len(menu) == 27
    first = menu[0]
    assert first.name == "Pasta and mushroom bake with sheep's cheese"
    assert first.counter == "COUNTER ONE"
    assert first.prices == {"students": "2,50", "employees": "4,40", "guests": "4,60"}
    assert first.codes == ["Mi", "Sl", "We"]
    assert first.pictograms == ["V"]
    assert first.image.startswith("assets/fotos/") and not first.side
    soup = next(m for m in menu if m.counter == "SOUP")
    assert soup.side
    # A placeholder photo is no photo; "&nbsp;" is no code.
    assert all("/dummies/" not in (m.image or "") for m in menu)
    assert all(c.strip() and "&" not in c for m in menu for c in m.codes)


def test_legend_codes_have_labels_and_kinds(legend):
    assert legend.labels["Mi"] == "Milk (incl. Lactose)" and legend.kinds["Mi"] == "allergen"
    assert legend.kinds["4"] == "additive"
    assert legend.labels["Kn"] == "with garlic" and legend.kinds["Kn"] == "note"
    assert legend.pictograms["V+"]["label"] == "vegan"


@pytest.mark.parametrize("question", [
    "What's in the Mensa today?", "Was gibt es morgen in der Mensa?", "Is there something vegan for lunch on Friday?",
    "gluten-free options in the canteen tomorrow?", "Speiseplan Wechloy", "Laktosefreie Gerichte heute?",
])
def test_menu_questions_are_recognised(question):
    assert menu_q.is_menu_question(question)


@pytest.mark.parametrize("question", [
    "What are the opening hours of the Mensa?", "Will canteen prices go up in 2026?",
    "How do I register for exams?", "Can I get a job in the Mensa?",
])
def test_other_questions_are_not(question):
    assert not menu_q.is_menu_question(question)


def test_day_canteen_and_wishes_are_read():
    r = menu_q.parse_request("Is there something vegan in Wechloy tomorrow?", THURSDAY, "en")
    assert r.day == date(2026, 10, 16) and r.locations == [3] and r.must_have == [{"V+"}]
    assert menu_q.parse_request("Mensa am Montag", THURSDAY, "de").day == date(2026, 10, 19)
    assert menu_q.parse_request("menu next Tuesday", THURSDAY, "en").day == date(2026, 10, 20)
    gluten = menu_q.parse_request("gluten-free food in the canteen", THURSDAY, "en")
    assert {"We", "Ro", "Ge"} <= gluten.no_codes
    halal = menu_q.parse_request("halal food in the mensa?", THURSDAY, "en")
    assert halal.halal and "S" in halal.no_pictograms and {"SG", "A"} <= halal.no_codes


def test_filters_choose_only_matching_meals(menu):
    vegan = [m for m in menu if menu_q.matches(m, menu_q.parse_request("vegan in the mensa", THURSDAY, "en"))]
    assert vegan and all("V+" in m.pictograms for m in vegan)
    no_gluten = [m for m in menu if menu_q.matches(m, menu_q.parse_request("gluten-free in the mensa", THURSDAY, "en"))]
    assert no_gluten and not any("We" in m.codes for m in no_gluten)


def test_answer_material_lists_only_matching_dishes_with_a_caution(offline):
    docs, payload = menu_q.answer_material("Gluten-free lunch in the Mensa today?", THURSDAY, "en")
    text = docs[0].page_content
    assert "Official menu of Mensa Uhlhornsweg for Thursday, 15 October 2026" in text
    assert "Pasta and mushroom bake" not in text  # contains wheat
    assert "ask the canteen staff" in text
    card = payload["menus"][0]
    assert card["date"] == "2026-10-15" and card["meals"]
    assert all("We" not in m["codes"] for m in card["meals"])
    assert {"code": "Mi", "label": "Milk (incl. Lactose)", "kind": "allergen"} in card["legend"]["codes"]
    assert payload["wishes"] == ["without gluten"] and payload["allergen_filter"] is True


def test_filter_labels_are_clean_and_in_the_question_language():
    assert menu_q.parse_request("Is there something vegetarian in the Mensa?", THURSDAY, "en").wishes == ["vegetarian"]
    assert menu_q.parse_request("Vegetarisches, laktosefreies Essen heute?", THURSDAY, "de").wishes == ["vegetarisch", "ohne Laktose"]
    halal = menu_q.parse_request("halal food in the mensa", THURSDAY, "en")
    assert halal.wishes == ["no pork", "no alcohol"]


def test_a_closed_day_moves_to_the_next_menu(offline):
    docs, payload = menu_q.answer_material("What's in the Mensa on Saturday?", THURSDAY, "en")
    assert "no menu for Saturday, 17 October 2026" in docs[0].page_content
    assert payload["menus"][0]["date"] == "2026-10-19"


def test_an_unreachable_menu_says_so_without_cards(monkeypatch, legend):
    monkeypatch.setattr(mensa, "get_legend", lambda lang="en": legend)
    monkeypatch.setattr(mensa, "get_menu", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("down")))
    docs, payload = menu_q.answer_material("What's in the Mensa today?", THURSDAY, "en")
    assert "could not be loaded" in docs[0].page_content and payload is None


def test_the_graph_answers_menus_from_the_menu_and_resets_the_cards(offline, monkeypatch):
    from langchain_core.messages import HumanMessage

    from graph import nodes

    monkeypatch.setattr(nodes, "_route_with_tools", lambda q: (_ for _ in ()).throw(AssertionError("router called")))
    out = nodes.retrieve_node({"messages": [HumanMessage(content="What's in the Mensa today?")], "source_id_filter": None})
    assert out["mensa"]["menus"] and out["time_sensitive"] is True
    assert out["retrieved_docs"][0].metadata["source_id"] == "mensa_menu" and out["direct_answer"]

    monkeypatch.setattr(nodes, "_route_with_tools", lambda q: None)
    monkeypatch.setattr(nodes, "_SpeculativeRetrieval", lambda q, f: type("R", (), {"result": lambda self: [], "cancel": lambda self: None})())
    other = nodes.retrieve_node({"messages": [HumanMessage(content="How do I register for exams?")], "source_id_filter": None})
    assert other["mensa"] is None


def test_menu_answers_are_never_reused():
    from db.semantic_cache import is_reusable_question

    assert not is_reusable_question("What's in the Mensa today?")
    assert is_reusable_question("How do I register for exams?")


def test_the_photo_proxy_accepts_only_menu_paths(client):
    assert client.get("/mensa/image", params={"src": "https://evil.example/x.jpg"}).status_code == 400
    assert client.get("/mensa/image", params={"src": "assets/fotos/../../etc/passwd.jpg"}).status_code == 400
    assert client.get("/mensa/image", params={"src": "assets/other/x.jpg"}).status_code == 400


def test_the_photo_proxy_fetches_once_then_serves_from_disk(client, monkeypatch, tmp_path):
    from api import routes_mensa

    monkeypatch.setattr(routes_mensa, "_cache_dir", lambda: tmp_path)
    fetched = []

    def fake_get(url, **kw):
        fetched.append(url)
        return httpx.Response(200, content=b"\xff\xd8jpeg", headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(routes_mensa.httpx, "get", fake_get)
    for _ in range(2):
        response = client.get("/mensa/image", params={"src": "assets/fotos/mensa-uhlhornsweg/Pasta/a_b.jpg"})
        assert response.status_code == 200 and response.content == b"\xff\xd8jpeg"
    assert fetched == [f"{routes_mensa.BASE_URL}/assets/fotos/mensa-uhlhornsweg/Pasta/a_b.jpg"]


def test_the_menu_answer_is_written_from_the_menu_not_by_the_model(offline):
    docs, payload, text = menu_q.menu_reply("Gluten-free lunch in the Mensa today?", THURSDAY, "en")
    assert text.startswith("**Mensa Uhlhornsweg**, Thursday, 15 October 2026")
    # Every dish line is a dish from the cards, with its name as published.
    names = {m["name"] for m in payload["menus"][0]["meals"]}
    dish_lines = [line for line in text.splitlines() if line.startswith("- **")]
    assert dish_lines and all(line[4:].split("**")[0] in names for line in dish_lines)
    assert "Pasta and mushroom bake" not in text and "allergen codes only" in text
    assert "Official menu:" in text

    _, _, german = menu_q.menu_reply("Was gibt es heute in der Mensa?", THURSDAY, "de")
    assert german.startswith("**Mensa Uhlhornsweg**, Donnerstag, 15. Oktober 2026")


def test_the_graph_gives_the_menu_answer_without_the_model(offline):
    from langchain_core.messages import HumanMessage

    from graph import nodes

    out = nodes.retrieve_node({"messages": [HumanMessage(content="What's in the Mensa today?")], "source_id_filter": None})
    assert out["direct_answer"].startswith("**Mensa Uhlhornsweg**")


def test_a_menu_answer_counts_as_answered():
    from graph.build_graph import _answered

    assert _answered("No dish here does not contain milk.", {"mensa": {"menus": [{"meals": []}]}})
    assert not _answered("The documents do not contain information on that.", {"mensa": None})
