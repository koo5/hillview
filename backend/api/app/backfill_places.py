#!/usr/bin/env python3
"""Reverse-geocode public photos and store place_name / place_slug / raw geocode.

Foundation for SEO place/area pages + JSON-LD contentLocation.name
(docs/todo/seo-place-aggregation-pages.md). Out-of-band backfill — NOT run at
upload time.

Geocoder-agnostic: talks to any Nominatim-compatible /reverse endpoint via
--geocoder-url. The public OSM Nominatim (default) is fine for small validation
runs but its usage policy FORBIDS bulk geocoding (~27k) — point --geocoder-url
at a self-hosted Nominatim/Photon for the full run.

Resumable: only touches photos with geocode IS NULL, so re-running continues.

Run inside the api container, e.g.:
  docker exec hillview_api sh -lc 'cd /app/app && \
    python3 backfill_places.py --filter curated --limit 60'
"""
import os
import sys
import time
import json
import re
import math
import unicodedata
import asyncio
import argparse
import urllib.parse
import urllib.request

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

from sqlalchemy import select, update, func, and_, or_
from common.database import SessionLocal
from common.models import Photo, PhotoAnnotation
from geoalchemy2.functions import ST_X, ST_Y


def slugify(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def derive_place(address: dict):
    """(place_name, place_slug) at neighborhood/town granularity, or (None, None).

    Prefer the most specific named place (neighbourhood/suburb/village/town) over
    administrative areas; never a street address.

    place_name is a human label: "<place>, <city>" (city omitted for standalone
    towns). place_slug must be globally unique and stable — the corpus spans
    multiple countries (CZ + ES) and Czech village names repeat across regions —
    so it carries a coarse admin tail: the city + country code for sub-city
    places, or the ISO-3166-2 region code (e.g. cz-20) for standalone towns.
    Coarse levels are used deliberately: they stay identical for every photo at
    the same place, so the place doesn't fragment into multiple slugs.
    """
    pick = (address.get('neighbourhood') or address.get('suburb') or address.get('quarter')
            or address.get('village') or address.get('town') or address.get('city_district')
            or address.get('municipality') or address.get('city') or address.get('county'))
    if not pick:
        return None, None
    city = address.get('city') or address.get('town') or address.get('municipality')
    cc = (address.get('country_code') or '').lower()
    iso2 = (address.get('ISO3166-2-lvl4') or '').lower()  # e.g. "cz-10"

    name = pick if (not city or city == pick) else f"{pick}, {city}"
    if city and city != pick:
        # Sub-city place (e.g. a Prague suburb): the city disambiguates within
        # the country; the country code guards against same-named places abroad.
        tail = [city, cc]
    else:
        # Standalone town/village: disambiguate at okres (district) level, since
        # village names repeat across districts. Prefer the readable okres name
        # ("okres Mělník" -> "melnik"); fall back to the ISO lvl5 okres code when
        # the town shares its okres's name (avoids "melnik-melnik"), then region.
        lvl5 = (address.get('ISO3166-2-lvl5') or '').lower()  # e.g. "cz-206"
        district = re.sub(r'^(okres|obvod)\s+', '', address.get('district') or '', flags=re.I)
        if district and slugify(district) != slugify(pick):
            tail = [district, cc]
        elif lvl5:
            tail = [lvl5]            # okres code already embeds the country
        else:
            tail = [iso2 or cc]      # region code / country fallback
    slug = slugify(' '.join([pick] + [t for t in tail if t]))
    return name, (slug or None)


def km_between(lat1, lon1, lat2, lon2):
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def reverse_geocode(base_url: str, lat: float, lon: float, zoom: int, max_km: float):
    q = urllib.parse.urlencode({
        'lat': lat, 'lon': lon, 'format': 'json', 'zoom': zoom, 'addressdetails': 1,
    })
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/reverse?{q}",
        headers={'User-Agent': 'hillview-place-backfill/1.0 (https://hillview.cz)'},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read())
    addr = data.get('address')
    if not addr:
        return None
    # Reject far matches: a coverage-limited instance (e.g. Czech-only) reverse-
    # geocoding a point outside its data snaps to the nearest object it has —
    # possibly hundreds of km away — which would mislabel the photo. Real matches
    # sit within a few km. Treated as "no coverage" (place left NULL, retriable).
    try:
        if km_between(lat, lon, float(data['lat']), float(data['lon'])) > max_km:
            return None
    except (KeyError, TypeError, ValueError):
        pass
    return {'address': addr, 'display_name': data.get('display_name')}


def _interesting():
    return or_(
        Photo.featured == True,
        and_(Photo.title.isnot(None), Photo.title != ""),
        and_(Photo.description.isnot(None), Photo.description != ""),
        func.array_length(Photo.keywords, 1) > 0,
        select(PhotoAnnotation.id).where(PhotoAnnotation.photo_id == Photo.id).exists(),
    )


async def rederive(opts):
    """Recompute place_name/place_slug from already-stored geocode JSONB — no
    network. Use after changing derive_place() to re-slug cheaply."""
    changed = 0
    async with SessionLocal() as db:
        rows = (await db.execute(
            select(Photo.id, Photo.geocode).where(Photo.geocode.isnot(None))
        )).all()
        for pid, geo in rows:
            name, slug = derive_place((geo or {}).get('address') or {})
            if opts.dry_run:
                print(f"  {pid} -> {name!r} [{slug}]", flush=True)
            else:
                await db.execute(update(Photo).where(Photo.id == pid)
                                 .values(place_name=name, place_slug=slug))
            changed += 1
        if not opts.dry_run:
            await db.commit()
    print(f"Re-derived {changed} rows.", flush=True)


async def main(opts):
    if opts.rederive:
        return await rederive(opts)
    done = 0
    no_addr = 0
    async with SessionLocal() as db:
        while opts.limit is None or done < opts.limit:
            batch_n = 200 if opts.limit is None else min(200, opts.limit - done)
            conds = [
                Photo.is_public == True,
                Photo.deleted == False,
                Photo.processing_status == "completed",
                Photo.geometry.isnot(None),
                # Default: only never-attempted rows. --retry-no-place also re-tries
                # rows attempted before but left placeless (e.g. out-of-coverage on
                # a Czech-only run) — point --geocoder-url at a global instance.
                Photo.place_slug.is_(None) if opts.retry_no_place else Photo.geocode.is_(None),
            ]
            if opts.filter == 'curated':
                conds.append(_interesting())
            rows = (await db.execute(
                select(Photo.id, ST_Y(Photo.geometry), ST_X(Photo.geometry))
                .where(*conds).limit(batch_n)
            )).all()
            if not rows:
                break
            for pid, lat, lon in rows:
                try:
                    geo = reverse_geocode(opts.geocoder_url, lat, lon, opts.zoom, opts.max_km)
                except Exception as e:
                    print(f"  {pid} geocode error: {e}", flush=True)
                    geo = None
                if geo is None:
                    no_addr += 1
                    # Mark as attempted so we don't loop forever on it.
                    geo = {'address': {}, 'display_name': None}
                name, slug = derive_place(geo['address'])
                if opts.dry_run:
                    print(f"  {lat:.5f},{lon:.5f} -> {name!r} [{slug}]", flush=True)
                else:
                    await db.execute(
                        update(Photo).where(Photo.id == pid)
                        .values(geocode=geo, place_name=name, place_slug=slug)
                    )
                done += 1
                if done % 25 == 0:
                    print(f"  ...{done} geocoded ({no_addr} no-address)", flush=True)
                time.sleep(opts.delay)
            if not opts.dry_run:
                await db.commit()
    print(f"Done: {done} geocoded, {no_addr} without a usable address.", flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geocoder-url', default='https://nominatim.openstreetmap.org',
                   help='Nominatim-compatible base URL (self-host for bulk!)')
    p.add_argument('--filter', choices=['all', 'curated'], default='all',
                   help="'curated' = only the interesting set (panos etc.) for validation")
    p.add_argument('--limit', type=int, default=None, help='max photos this run')
    p.add_argument('--delay', type=float, default=1.1, help='seconds between requests')
    p.add_argument('--zoom', type=int, default=16, help='Nominatim zoom (granularity)')
    p.add_argument('--max-km', type=float, default=5.0,
                   help='reject matches farther than this from the photo (guards '
                        'coverage-limited instances snapping to a far place)')
    p.add_argument('--retry-no-place', action='store_true',
                   help='also re-attempt rows geocoded before but left placeless '
                        '(e.g. out-of-coverage); pair with a global --geocoder-url')
    p.add_argument('--dry-run', action='store_true', help='print, do not write')
    p.add_argument('--rederive', action='store_true',
                   help='recompute place_name/place_slug from stored geocode (no network)')
    asyncio.run(main(p.parse_args()))
