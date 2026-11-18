"""Interactive place search against the same Nominatim instance as the backfill."""
import logging
import math
import os

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ValidationError

from rate_limiter import general_rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/places", tags=["places"])


class PlaceResult(BaseModel):
    id: str
    name: str
    display_name: str = Field(min_length=1)
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    # Nominatim order: south, north, west, east.
    bounds: tuple[float, float, float, float] | None = None


def place_bounds(value):
    """An absent or unusable extent still leaves a usable point result."""
    try:
        south, north, west, east = map(float, value)
        if (all(math.isfinite(v) for v in (south, north, west, east))
                and -90 <= south <= north <= 90 and -180 <= west <= east <= 180):
            return south, north, west, east
    except (TypeError, ValueError):
        pass
    return None


@router.get("/search", response_model=list[PlaceResult])
async def search_places(
    request: Request,
    response: Response,
    q: str = Query(min_length=2, max_length=200),
):
    await general_rate_limiter.enforce_rate_limit(request, "public_read")
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "Enter at least two characters to search.")

    base_url = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")
    if not base_url:
        raise HTTPException(503, "Place search is not configured.")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            result = await client.get(
                f"{base_url}/search",
                params={"q": query, "format": "jsonv2", "limit": 10},
                headers={"User-Agent": "hillview-place-search/1.0 (https://hillview.cz)"},
            )
            result.raise_for_status()
            data = result.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "Place search timed out. Please try again.") from None
    except (httpx.HTTPError, ValueError):
        logger.warning("Nominatim search request failed", exc_info=True)
        raise HTTPException(502, "Place search is temporarily unavailable.") from None

    if not isinstance(data, list):
        raise HTTPException(502, "Place search returned an invalid response.")
    places = []
    try:
        for item in data[:10]:
            places.append(PlaceResult(
                id=str(item["place_id"]),
                name=item.get("name") or item["display_name"].split(",")[0],
                display_name=item["display_name"],
                lat=item["lat"],
                lon=item["lon"],
                bounds=place_bounds(item.get("boundingbox")),
            ))
    except (KeyError, TypeError, AttributeError, ValidationError):
        raise HTTPException(502, "Place search returned an invalid response.") from None

    response.headers["Cache-Control"] = "public, max-age=300"
    return places
