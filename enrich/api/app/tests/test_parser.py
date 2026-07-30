from app.parser import parse_body


def test_full_form():
    p = parse_body("Ještěd | highest point | https://cs.wikipedia.org/wiki/Ještěd | 50.732N, 15.008E")
    assert p.name == "Ještěd"
    assert p.context == "highest point"
    assert p.wiki == ("cs", "Ještěd")
    assert p.wiki_url == "https://cs.wikipedia.org/wiki/Ještěd"
    assert p.coords == (50.732, 15.008)   # (lat, lon)
    assert not p.uncertain and not p.oops and not p.unnamed


def test_bare_name():
    p = parse_body("Petřín")
    assert p.name == "Petřín" and p.context is None and p.coords is None
    assert not p.unnamed and not p.uncertain


def test_uncertain_trailing_q():
    p = parse_body("Vysočany?")
    assert p.name == "Vysočany"
    assert p.uncertain is True and p.unnamed is False


def test_uncertain_inline():
    p = parse_body("O2 Arena (?)")
    assert p.name == "O2 Arena"
    assert p.uncertain is True


def test_unnamed_bare_q():
    p = parse_body("?")
    assert p.unnamed is True and p.name is None


def test_empty():
    p = parse_body("")
    assert p.unnamed is True and p.name is None and p.segments == []


def test_oops():
    p = parse_body("oops | stitching seam here")
    assert p.oops is True
    # oops is a fact, not a skip; name still parsed but type_guess suppressed
    assert p.type_guess is None


def test_oops_prefix():
    p = parse_body("oopsie wrong")
    assert p.oops is True


def test_coords_only_segment():
    p = parse_body("Some Hill | 50.100N 14.500E")
    assert p.name == "Some Hill"
    assert p.coords == (50.100, 14.500)
    # 2nd segment is coords => not used as context
    assert p.context is None


def test_url_second_segment_not_context():
    p = parse_body("Kostel | https://en.wikipedia.org/wiki/Church")
    assert p.name == "Kostel"
    assert p.context is None
    assert p.wiki == ("en", "Church")


def test_type_guess():
    assert parse_body("Žižkovská věž").type_guess == "tower"
    assert parse_body("kostel svatého Víta").type_guess == "church"
    assert parse_body("Pražský hrad").type_guess == "castle"
    assert parse_body("Random Building").type_guess is None


def test_type_guess_word_boundaries():
    # v1 substring-matched keywords inside longer words
    assert parse_body("Zahradní město").type_guess is None      # "hrad" in Zahradní
    assert parse_body("Vrchlického sady").type_guess is None    # "vrch" in Vrchlického
    assert parse_body("hrad Bezděz").type_guess == "castle"
    assert parse_body("Bezděz (hrad)").type_guess == "castle"
