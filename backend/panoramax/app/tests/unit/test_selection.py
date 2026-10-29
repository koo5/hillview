"""Global thinning, compass wrap-around, and daylight preference."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import permutations
import math

import pytest

from selection import Candidate, bearing_bucket, daylight_rank, select_photos, solar_elevation

NOON = datetime(2024, 6, 21, 12)


def photo(id='photo', **changes):
    return replace(Candidate(id=id, owner_id='owner', effective_at=NOON, captured_at=NOON,
        longitude=0, latitude=50, bearing=0, grid_srid=32631, grid_x=100000, grid_y=1100000), **changes)


@pytest.mark.parametrize('bearing,expected', [
    (0, 0), (360, 0), (-360, 0), (359.9, 0), (-1, 0),
    (22.499, 0), (22.5, 1), (45, 1), (67.5, 2), (90, 2),
    (135, 3), (180, 4), (225, 5), (270, 6), (315, 7),
    (337.499, 7), (337.5, 0), (None, -1), (math.nan, -1), (math.inf, -1),
])
def test_compass_sectors(bearing, expected):
    assert bearing_bucket(bearing) == expected


def test_configurable_sector_width():
    assert bearing_bucket(11.249, 16) == 0
    assert bearing_bucket(11.25, 16) == 1
    assert bearing_bucket(348.75, 16) == 0


@pytest.mark.parametrize('count', [0, -1, 361])
def test_invalid_sector_count(count):
    with pytest.raises(ValueError):
        select_photos([], count)


def test_daylight_uses_location_and_season():
    assert solar_elevation(NOON, 50, 0) > 60
    assert solar_elevation(NOON.replace(hour=0), 50, 0) < -10
    assert 10 < solar_elevation(NOON.replace(month=12), 50, 0) < 20
    assert solar_elevation(NOON, 0, 180) < -60
    assert solar_elevation(NOON, 0, -180) == pytest.approx(solar_elevation(NOON, 0, 180))


@pytest.mark.parametrize('hour', [0, 6, 12, 18])
def test_polar_day_and_night(hour):
    at = NOON.replace(hour=hour)
    assert solar_elevation(at, 85, 0) > 0
    assert solar_elevation(at.replace(month=12), 85, 0) < 0
    assert solar_elevation(at, -85, 0) < 0
    assert solar_elevation(at.replace(month=12), -85, 0) > 0


def test_naive_datetimes_are_utc_and_offsets_are_respected():
    utc = NOON.replace(tzinfo=timezone.utc)
    local = utc.astimezone(timezone(timedelta(hours=12)))
    assert solar_elevation(NOON, 50, 14) == solar_elevation(utc, 50, 14)
    assert solar_elevation(local, 50, 14) == solar_elevation(utc, 50, 14)
    assert math.isfinite(solar_elevation(datetime(2024, 2, 29, 12), 50, 14))


def test_upload_time_does_not_claim_to_be_daylight():
    assert daylight_rank(photo(captured_at=None)) == 1
    assert daylight_rank(photo()) == 2
    assert daylight_rank(photo(captured_at=NOON.replace(hour=0))) == 0


def test_global_winner_prefers_daylight_then_capture_recency_then_id():
    older = photo('a-old', owner_id='one')
    newer = photo('b-new', owner_id='two', captured_at=NOON + timedelta(days=1))
    tied = replace(newer, id='a-tie')
    night = photo('night', captured_at=NOON.replace(year=2026, hour=0))
    unknown = photo('unknown', captured_at=None, effective_at=NOON.replace(year=2026))
    for order in permutations([older, newer, tied, night, unknown]):
        assert [p.id for p in select_photos(list(order))] == ['a-tie']


def test_a_night_photo_can_fill_a_bucket_and_fallback_promotes_the_next_candidate():
    day = photo('day')
    night = photo('night', captured_at=NOON.replace(hour=0))
    assert select_photos([night, day]) == [day]
    assert select_photos([night]) == [night]
    assert select_photos([]) == []


def test_unknown_capture_time_is_preferred_to_known_night_and_uses_effective_recency():
    night = photo('night', captured_at=NOON.replace(hour=0))
    unknown = photo('unknown', captured_at=None)
    newer = photo('newer', captured_at=None, effective_at=NOON + timedelta(days=1))
    assert select_photos([night, unknown, newer]) == [newer]


def test_only_photos_in_the_same_cell_and_sector_compete():
    original = photo('north', bearing=359)
    candidates = [original,
        photo('north-east', bearing=45), photo('unknown', bearing=None),
        photo('east-cell', grid_x=100001), photo('north-cell', grid_y=1100001),
        photo('other-zone', grid_srid=32632), photo('other-hemisphere', grid_srid=32731)]
    assert select_photos(candidates) == candidates


def test_selection_preserves_capture_order_for_session_ranking():
    older = photo('older')
    other_cell = photo('middle', grid_x=100001)
    winner = photo('winner', captured_at=NOON + timedelta(days=1))
    assert select_photos([older, other_cell, winner]) == [other_cell, winner]
