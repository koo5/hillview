"""Unit tests for legal_rights_to_license mapping in hillview_routes."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from hillview_routes import legal_rights_to_license, LEGAL_RIGHTS_TO_LICENSE


class TestLegalRightsToLicense:
    def test_full1_maps_to_arr(self):
        assert legal_rights_to_license('full1') == 'arr'

    def test_ccbysa4_osm_maps_to_itself(self):
        assert legal_rights_to_license('ccbysa4+osm') == 'ccbysa4+osm'

    def test_none_falls_back_to_arr(self):
        # Defensive default: a photo with no recorded legal_rights should
        # not be implicitly treated as openly licensed.
        assert legal_rights_to_license(None) == 'arr'

    def test_empty_string_falls_back_to_arr(self):
        assert legal_rights_to_license('') == 'arr'

    def test_unknown_identifier_returned_as_is(self):
        # Forward compatibility: new identifiers added in newer backends
        # should survive a round-trip even without an entry in the map.
        assert legal_rights_to_license('future-license-v99') == 'future-license-v99'

    def test_all_mapped_identifiers_yield_non_empty_strings(self):
        for internal, public in LEGAL_RIGHTS_TO_LICENSE.items():
            assert isinstance(internal, str) and internal
            assert isinstance(public, str) and public
