from app.parser import parse_body


def test_wiki_title_keeps_balanced_parens():
    # parser v5: the disambiguator's ")" used to be dropped, so the coords lookup
    # for every "(Place)"-titled church/castle page failed downstream
    p = parse_body("Kostel svatého Petra a Pavla (Čáslav)|https://cs.wikipedia.org/wiki/Kostel_svatého_Petra_a_Pavla_(Čáslav)")
    assert p.wiki_url == "https://cs.wikipedia.org/wiki/Kostel_svatého_Petra_a_Pavla_(Čáslav)"
    assert p.wiki == ("cs", "Kostel svatého Petra a Pavla (Čáslav)")
    p = parse_body("Kostel (Malín)|https://cs.wikipedia.org/wiki/Kostel_svat%C3%A9ho_%C5%A0t%C4%9Bp%C3%A1na_(Mal%C3%ADn)")
    assert p.wiki_url.endswith("_(Mal%C3%ADn)")
    assert p.wiki == ("cs", "Kostel svatého Štěpána (Malín)")


def test_wiki_url_wrapped_in_parens_stops_before_the_wrapper():
    p = parse_body("Bezděz | (https://cs.wikipedia.org/wiki/Bezděz_(hrad))")
    assert p.wiki_url == "https://cs.wikipedia.org/wiki/Bezděz_(hrad)"


def test_wiki_url_drops_query_and_fragment_and_mobile_host():
    # parser v6: mobile share links append ?uselang=en; the title is the path only
    p = parse_body("Kostel Všech svatých (Sedlec)|https://cs.wikipedia.org/wiki/Kostel%20V%C5%A1ech%20svat%C3%BDch%20(Sedlec)?uselang=en")
    assert p.wiki_url == "https://cs.wikipedia.org/wiki/Kostel%20V%C5%A1ech%20svat%C3%BDch%20(Sedlec)"
    assert p.wiki == ("cs", "Kostel Všech svatých (Sedlec)")
    p = parse_body("https://cs.m.wikipedia.org/wiki/Pet%C5%99%C3%ADnsk%C3%A1_rozhledna#Historie")
    assert p.wiki_url == "https://cs.wikipedia.org/wiki/Pet%C5%99%C3%ADnsk%C3%A1_rozhledna"
    assert p.links == []


def test_wiki_only_body_takes_the_title_as_label():
    p = parse_body("https://cs.wikipedia.org/wiki/Vod%C3%A1rensk%C3%A1_v%C4%9B%C5%BE_(D%C4%9Bv%C3%ADn)")
    assert p.unnamed and p.name == "Vodárenská věž (Děvín)"


def test_hillview_link_with_only_lat_lon_is_coords():
    p = parse_body("cerna vez|https://hillview.cz/?lat=50.09194&lon=14.40499&zoom=16")
    assert p.coords == (50.09194, 14.40499) and p.coords_from_link
    assert p.links == ["https://hillview.cz/?lat=50.09194&lon=14.40499&zoom=16"]
    assert p.roles == ["name", "url"]


def test_hillview_link_to_a_photo_view_is_just_a_link():
    body = "Kostel cakovice|https://hillview.cz/?lat=50.151625&lon=14.5234361111111&zoom=16&bearing=180.83&photo=hillview-c39895fd"
    p = parse_body(body)
    assert p.coords is None and not p.coords_from_link
    assert p.links == [body.split("|")[1]]


def test_poi_key_segment():
    # parser v7: "id=<key>" is the author's handle for the subject, not a label
    p = parse_body("id=vcelka")
    assert p.poi_key == "vcelka" and p.unnamed and p.name is None and p.roles == ["poiKey"]
    p = parse_body("Včelka | id=vcelka | 50.123, 14.456")
    assert p.name == "Včelka" and p.poi_key == "vcelka" and p.coords == (50.123, 14.456)
    assert p.roles == ["name", "poiKey", "coords"]


def test_explicit_coords_beat_a_hillview_link():
    p = parse_body("x | 50.123, 14.456 | https://hillview.cz/?lat=50.09194&lon=14.40499")
    assert p.coords == (50.123, 14.456) and not p.coords_from_link


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


def test_coords_hemisphere_sign():
    # v4: S/W negate; N/E and letterless stay positive
    assert parse_body("? | 33.8568S, 151.2153E").coords == (-33.8568, 151.2153)
    assert parse_body("? | 40.7128N, 74.0060W").coords == (40.7128, -74.006)
    assert parse_body("? | 50.732, 15.008").coords == (50.732, 15.008)


def test_coords_signed_decimals():
    assert parse_body("? | -33.8568, 151.2153").coords == (-33.8568, 151.2153)
    assert parse_body("? | 40.7128, -74.0060").coords == (40.7128, -74.006)


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
