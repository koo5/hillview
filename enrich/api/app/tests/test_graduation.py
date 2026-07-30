"""suggest_body: the graduation serializer — approved facts → suggested body.
This is the text that would one day be written back into Hillview annotations,
so its behavior is pinned: in-place segment edits, verbatim preservation of
anything unmodeled, idempotency, and parse_body round-trip."""
from app.parser import parse_body
from app.routers.graduation import suggest_body

ANCHOR = (50.05422, 14.46877)


def test_bare_question_mark():
    s, ch = suggest_body("?", "Plynárna Michle - komín 1", ANCHOR, None)
    assert s == "Plynárna Michle - komín 1 | 50.05422N, 14.46877E"
    assert {c["what"]: (c["from"], c["to"]) for c in ch} == {
        "label": ("?", "Plynárna Michle - komín 1"),
        "coords": (None, "50.05422N, 14.46877E")}


def test_coords_appended_to_plain_name():
    s, ch = suggest_body("koh-i-noor", None, ANCHOR, None)
    assert s == "koh-i-noor | 50.05422N, 14.46877E"
    assert [c["what"] for c in ch] == ["coords"]


def test_unmodeled_url_segment_preserved():
    body = "OK1KHL|https://www.ok1khl.com/view.php?cisloclanku=2026021501"
    s, _ = suggest_body(body, None, ANCHOR, None)
    assert s == ("OK1KHL | https://www.ok1khl.com/view.php?cisloclanku=2026021501"
                 " | 50.05422N, 14.46877E")


def test_coords_replaced_in_place_others_verbatim():
    body = "Ještěd | highest point | https://cs.wikipedia.org/wiki/Ještěd | 50.732N, 15.008E"
    s, ch = suggest_body(body, None, (50.73280, 15.01000), None)
    assert s == ("Ještěd | highest point | https://cs.wikipedia.org/wiki/Ještěd"
                 " | 50.73280N, 15.01000E")
    assert ch[0]["from"] == "50.732N, 15.008E"


def test_same_coords_at_5dp_no_change():
    body = "X | 50.05422N, 14.46877E"
    s, ch = suggest_body(body, None, ANCHOR, None)
    assert s == body
    assert ch == []


def test_wiki_anchor_appended_once():
    wiki = "https://cs.wikipedia.org/wiki/Je%C5%A1t%C4%9Bd"
    s, ch = suggest_body("Ještěd", None, (50.73280, 15.01000), wiki)
    assert s == "Ještěd | 50.73280N, 15.01000E | " + wiki
    # already present → not duplicated, no wiki change
    s2, ch2 = suggest_body(s, None, (50.73280, 15.01000), wiki)
    assert s2 == s
    assert ch2 == []


def test_idempotent_and_round_trips():
    s, _ = suggest_body("?", "Plynárna Michle - komín 1", ANCHOR, None)
    s2, ch2 = suggest_body(s, "Plynárna Michle - komín 1", ANCHOR, None)
    assert s2 == s and ch2 == []
    p = parse_body(s)
    assert p.name == "Plynárna Michle - komín 1"
    assert p.coords == ANCHOR
    assert not p.unnamed and not p.uncertain


def test_wiki_without_anchor():
    # attached page, no anchor coords: wiki segment appended, nothing else touched
    wiki = "https://cs.wikipedia.org/wiki/Plyn%C3%A1rna_Michle"
    s, ch = suggest_body("Plynárna Michle - komín 1 | 50.05422N, 14.46877E",
                         None, None, wiki)
    assert s == "Plynárna Michle - komín 1 | 50.05422N, 14.46877E | " + wiki
    assert [c["what"] for c in ch] == ["wiki"]
    p = parse_body(s)
    assert p.wiki_url == wiki and p.coords == ANCHOR


def test_empty_body_gets_placeholder_name():
    s, _ = suggest_body(None, None, ANCHOR, None)
    assert s == "? | 50.05422N, 14.46877E"
    assert parse_body(s).unnamed
