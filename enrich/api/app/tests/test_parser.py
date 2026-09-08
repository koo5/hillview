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


def test_osmap_link_poi_is_the_authors_osm_object():
    # parser v8: poi=type:id in the fragment is the selected OSM object; the
    # map= centre must NOT become coords when a poi= is present (a duplicate
    # geo: pin would outrank the exact object in the anchor picker)
    p = parse_body("https://osmap.vfosnar.cz/#base=carto&map=19/48.94187/15.72672&poi=way:46934757")
    assert p.osm_ref == "way:46934757"
    assert p.coords is None
    assert p.unnamed
    assert p.links == ["https://osmap.vfosnar.cz/#base=carto&map=19/48.94187/15.72672&poi=way:46934757"]


def test_osmap_link_after_name_and_layers():
    p = parse_body("hotel occidental praha|https://osmap.vfosnar.cz/#base=cuzk&layers=contours,fody,pistes,hiking,osm-notes&map=16/50.04367/14.43952&poi=way:22540879")
    assert p.name == "hotel occidental praha"
    assert p.osm_ref == "way:22540879"
    assert p.coords is None


def test_osmap_poi_node():
    p = parse_body("https://osmap.vfosnar.cz/#base=carto&map=17/50.08118/14.49946&layers=contours&poi=node:4020587067")
    assert p.osm_ref == "node:4020587067"


def test_osmap_map_centre_is_fallback_coords_without_poi():
    p = parse_body("https://osmap.vfosnar.cz/#base=carto&map=17/50.08118/14.49946&layers=contours")
    assert p.osm_ref is None
    assert p.coords == (50.08118, 14.49946)
    assert p.coords_from_link


def test_osmap_body_coords_beat_the_map_centre():
    p = parse_body("Vrch | 50.10000N, 14.40000E | https://osmap.vfosnar.cz/#map=17/50.08118/14.49946")
    assert p.coords == (50.1, 14.4)
    assert not p.coords_from_link


def test_dms_coords_parse():
    # parser v9: DMS as copied from vezovevodojemy.cz / GPS listings
    p = parse_body('Vodojem | 50°10\'29.869"N, 14°38\'52.907"E')
    assert p.coords == (50.1749636, 14.6480297)
    assert p.roles == ["name", "coords"]
    # decimal minutes (DDM)
    p = parse_body("x | 50°10.4978'N 14°38.8818'E")
    assert p.coords is not None
    assert abs(p.coords[0] - 50.17496) < 1e-4 and abs(p.coords[1] - 14.64803) < 1e-4


def test_dms_bare_pair_in_name_slot_is_coords_not_name():
    p = parse_body('50°10\'29.869"N, 14°38\'52.907"E |https://example.org/x')
    assert p.unnamed
    assert p.coords == (50.1749636, 14.6480297)


def test_dms_needs_hemisphere_letters_so_prose_is_safe():
    p = parse_body("kotel | 12°C, 1500 m")
    assert p.coords is None
    # southern/western letters sign the values
    p = parse_body("x | 33°51'25.4\"S, 151°12'55.1\"E")
    assert p.coords is not None and p.coords[0] < 0 < p.coords[1]
