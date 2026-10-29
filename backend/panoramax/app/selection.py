"""Thin eligible contributions to one photo per 5 m cell and bearing sector.

Membership is still persisted by the sequencer, so reads never have to rank
the entire photo library. Selection is global across owners, deterministic,
and independent of which photo happened to be harvested first.
"""
from calendar import isleap
from dataclasses import dataclass
from datetime import datetime, timezone
import math

from eligibility import ELIGIBLE_PHOTO_WHERE, PHOTO_ORDER_BY

CELL_SIZE_M = 5
DEFAULT_BEARING_BUCKETS = 8

# UTM gives metre coordinates locally, rather than Mercator's latitude-dependent
# ground scale. Include the SRID in the cell key: zones and hemispheres have
# separate origins. UPS covers the polar caps. These are regular six-degree
# longitude zones (not MGRS's exceptional Norway/Svalbard zone boundaries).
# https://earth-info.nga.mil/?action=coordsys&dir=coordsys
# CASE guards invalid legacy coordinates before calling PROJ. Canonicalizing
# +180 to -180 also puts the two spellings of the date line in the same grid.
CANDIDATES_SQL = f"""
    WITH eligible AS MATERIALIZED (
        SELECT p.id, p.owner_id, p.effective_at, p.captured_at, p.original_filename,
               p.compass_angle AS bearing,
               CASE WHEN abs(ST_Y(p.geometry)) = 90 THEN 0
                    WHEN ST_X(p.geometry) = 180 THEN -180 ELSE ST_X(p.geometry) END AS longitude,
               ST_Y(p.geometry) AS latitude
        FROM photos p JOIN users u ON u.id = p.owner_id
        WHERE {ELIGIBLE_PHOTO_WHERE}
    ), projected AS MATERIALIZED (
        SELECT *, CASE WHEN longitude BETWEEN -180 AND 180 AND latitude BETWEEN -90 AND 90
            THEN ST_Transform(ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                CASE WHEN latitude >= 84 THEN 32661
                     WHEN latitude < -80 THEN 32761
                     ELSE (CASE WHEN latitude >= 0 THEN 32600 ELSE 32700 END)
                          + floor((longitude + 180) / 6)::integer + 1 END)
            END AS grid_point
        FROM eligible
    )
    SELECT p.id, p.owner_id, p.effective_at, p.captured_at, p.longitude, p.latitude, p.bearing,
           ST_SRID(p.grid_point) AS grid_srid,
           floor(ST_X(p.grid_point) / {CELL_SIZE_M})::bigint AS grid_x,
           floor(ST_Y(p.grid_point) / {CELL_SIZE_M})::bigint AS grid_y
    FROM projected p
    WHERE p.grid_point IS NOT NULL
    ORDER BY p.owner_id, {PHOTO_ORDER_BY}
"""


@dataclass(frozen=True)
class Candidate:
    id: str
    owner_id: str
    effective_at: datetime
    captured_at: datetime | None
    longitude: float
    latitude: float
    bearing: float | None
    grid_srid: int
    grid_x: int
    grid_y: int


def bearing_bucket(bearing: float | None, buckets: int = DEFAULT_BEARING_BUCKETS) -> int:
    """Sectors centered on compass points; unknown is separate from true north.

    With eight sectors, north is [337.5°, 22.5°), NE is [22.5°, 67.5°), etc.
    Non-finite legacy bearings join the unknown bucket instead of aborting a pass.
    """
    if not 1 <= buckets <= 360:
        raise ValueError('bearing buckets must be between 1 and 360')
    if bearing is None or not math.isfinite(bearing):
        return -1
    return math.floor(((bearing % 360) * buckets / 360 + 0.5) % buckets)


def _utc(at: datetime) -> datetime:
    # photos.captured_at/effective_at are naive UTC in the database; also
    # accept aware timestamps for callers and tests without local-TZ guesses.
    return at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at.astimezone(timezone.utc)


def solar_elevation(at: datetime, latitude: float, longitude: float) -> float:
    """Approximate geometric solar elevation, in degrees, at a capture.

    NOAA's general solar-position equations handle longitude, seasons and polar
    day/night without a time-zone database or a network lookup. This ranks
    likely daylight, not exposure/image quality; terrain and weather are unknown.
    https://gml.noaa.gov/grad/solcalc/solareqns.PDF
    """
    at = _utc(at)
    hour = at.hour + at.minute / 60 + at.second / 3600 + at.microsecond / 3_600_000_000
    gamma = 2 * math.pi / (366 if isleap(at.year) else 365) * (at.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.001480 * math.sin(3 * gamma))
    angle = math.radians(((hour * 60 + eqtime + 4 * longitude) / 4 - 180) % 360)
    lat = math.radians(latitude)
    sin_elevation = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elevation))))


def daylight_rank(photo: Candidate) -> int:
    """Known daylight > unknown capture time > known night.

    Never mistake the upload-time fallback in effective_at for a capture time.
    Zero elevation is deliberately a rough daylight boundary, not a precise
    sunrise calculation with atmospheric refraction.
    """
    if photo.captured_at is None:
        return 1
    return 2 if solar_elevation(photo.captured_at, photo.latitude, photo.longitude) >= 0 else 0


def select_photos(photos: list[Candidate], buckets: int = DEFAULT_BEARING_BUCKETS) -> list[Candidate]:
    """Daylight first, then newest capture (effective time if unknown), then
    lexicographically smallest photo id. Preserve the input's session ordering.

    All candidates have already passed the eligibility gates. An ineligible
    winner therefore yields to the next-best candidate on the next pass, without
    a separate winners table or a record of who arrived first.
    """
    if not 1 <= buckets <= 360:
        raise ValueError('bearing buckets must be between 1 and 360')
    winners: dict[tuple[int, int, int, int], tuple[tuple[int, datetime], Candidate]] = {}
    for photo in photos:
        cell = (photo.grid_srid, photo.grid_x, photo.grid_y, bearing_bucket(photo.bearing, buckets))
        score = (daylight_rank(photo), _utc(photo.captured_at or photo.effective_at))
        previous = winners.get(cell)
        if previous is None or score > previous[0] or (score == previous[0] and photo.id < previous[1].id):
            winners[cell] = (score, photo)
    ids = {photo.id for _, photo in winners.values()}
    return [photo for photo in photos if photo.id in ids]
