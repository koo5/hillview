"""Unit tests for place-name derivation from a Nominatim address.

Czech data puts administrative units in the same fields as real place names, so
picking purely by granularity silently degrades: Prague's `suburb` holds the
správní obvod ("SO Praha 10") while the neighbourhood ("Spořilov") sits in
`quarter`. Stripping the "SO " prefix then hides the mistake, because the unit
starts reading like a place. All addresses below are real, from the corpus.
"""
from backfill_places import derive_place, derive_parent


def test_neighbourhood_beats_the_administrative_district_it_sits_in():
	# The photo that surfaced this: stored as "Praha 10, Praha" for years.
	address = {
		"road": "Zárybničná", "quarter": "Spořilov", "borough": "Praha 4",
		"suburb": "SO Praha 10", "district": "obvod Praha 10", "city": "Praha",
		"country_code": "cz", "ISO3166-2-lvl4": "CZ-10",
	}
	assert derive_place(address)[0] == "Spořilov, Praha"


def test_a_suburb_holding_a_real_name_still_wins():
	# Not every `suburb` is administrative — this ordering must not regress.
	assert derive_place({"suburb": "Prosek", "city": "Praha", "country_code": "cz"})[0] == "Prosek, Praha"
	assert derive_place(
		{"suburb": "Sedlec", "city": "Kutná Hora", "country_code": "cz"}
	)[0] == "Sedlec, Kutná Hora"


def test_an_administrative_unit_beats_naming_the_whole_city():
	# Nothing finer exists here, so the obvod is the most useful answer left —
	# "Praha" alone would throw away the only locality the address carries.
	assert derive_place(
		{"suburb": "SO Praha 9", "city": "Praha", "country_code": "cz"}
	)[0] == "Praha 9, Praha"


def test_a_town_outside_prague_is_not_labelled_with_a_prague_district():
	# Hostivice is in okres Praha-západ; the Praha 6 values are OSM boundary
	# artifacts. The old ordering produced the nonsense "Praha 6, Hostivice".
	address = {
		"city": "SO POÚ Hostivice", "road": "Čsl. armády", "town": "Hostivice",
		"region": "Středočeský kraj", "suburb": "SO Praha 6", "borough": "Praha 6",
		"district": "okres Praha-západ", "country_code": "cz",
		"municipality": "SO ORP Černošice", "ISO3166-2-lvl4": "CZ-20",
	}
	assert derive_place(address)[0] == "Hostivice"


def test_no_usable_place_yields_nothing():
	assert derive_place({"road": "Zárybničná", "country_code": "cz"}) == (None, None)


def test_parent_strips_administrative_prefixes():
	assert derive_parent({"city": "SO POÚ Hostivice", "country_code": "cz"})[0] == "Hostivice"
	assert derive_parent({"road": "Zárybničná"}) == (None, None)
