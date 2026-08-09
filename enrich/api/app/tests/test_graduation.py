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


def test_comma_decimal_coords_replaced_not_appended():
    # the RKS Liblice regression: Czech decimal-comma coords went unrecognized,
    # so the approved anchor was APPENDED and the body carried coordinates twice
    body = "RKS Liblice 2 - jih| 50,0620061, 14,8864855"
    s, ch = suggest_body(body, None, (50.06198, 14.88649), None)
    assert s == "RKS Liblice 2 - jih | 50.06198N, 14.88649E"
    assert [c["what"] for c in ch] == ["coords"]
    assert ch[0]["from"] == "50,0620061, 14,8864855"
    # and the canonical result is stable
    s2, ch2 = suggest_body(s, None, (50.06198, 14.88649), None)
    assert s2 == s and ch2 == []


def test_comma_decimal_coords_parse():
    p = parse_body("RKS Liblice 2 - jih| 50,0620061, 14,8864855")
    assert p.coords == (50.0620061, 14.8864855)
    assert p.roles == ["name", "coords"]
    assert p.context is None          # v2 misfiled the coords segment as context
    assert p.name == "RKS Liblice 2 - jih"


def test_roles_full_body():
    p = parse_body("Ještěd | highest point | https://cs.wikipedia.org/wiki/Ještěd"
                   " | 50.732N, 15.008E")
    assert p.roles == ["name", "context", "wiki", "coords"]


def test_long_decimal_coords_replaced_url_segment_verbatim():
    body = ("Sídliště Lehovec |50.10294800206575, 14.548184982903308"
            " |https://maps.app.goo.gl/s6s1cWJ8rFMZwGYQ6")
    s, ch = suggest_body(body, None, (50.10300, 14.54820), None)
    assert s == ("Sídliště Lehovec | 50.10300N, 14.54820E"
                 " | https://maps.app.goo.gl/s6s1cWJ8rFMZwGYQ6")
    assert [c["what"] for c in ch] == ["coords"]


def test_label_takes_over_pure_coords_body():
    # a body that is ONLY coordinates has no name; the label claims the name
    # slot and the anchor is appended, never overwriting the label again
    p = parse_body("50.732, 15.008")
    assert p.roles == ["coords"] and p.unnamed
    s, ch = suggest_body("50.732, 15.008", "Ještěd", (50.73280, 15.01000), None)
    assert s == "Ještěd | 50.73280N, 15.01000E"
    assert [c["what"] for c in ch] == ["label", "coords"]


def test_url_first_body_is_unnamed():
    p = parse_body("https://www.ok1khl.com/view.php?cisloclanku=2026021501")
    assert p.roles == ["url"] and p.unnamed and p.name is None
