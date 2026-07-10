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


# Czech administrative-area prefixes Nominatim sometimes returns in place of a
# clean town/district name ("SO POÚ Říčany" -> "Říčany", "SO Praha 6" -> "Praha
# 6"). Longer forms first so "SO POÚ" isn't half-stripped to "POÚ ...".
_ADMIN_PREFIX = re.compile(r'^(SO\s+POÚ|SO\s+ORP|SO|ORP|POÚ|MČ|obvod|okres)\s+', re.I)


def _clean_admin(s):
    return _ADMIN_PREFIX.sub('', s).strip() if s else s


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
    pick = _clean_admin(address.get('neighbourhood') or address.get('suburb') or address.get('quarter')
            or address.get('village') or address.get('town') or address.get('city_district')
            or address.get('municipality') or address.get('city') or address.get('county'))
    if not pick:
        return None, None
    city = _clean_admin(address.get('city') or address.get('town') or address.get('municipality'))
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
        district = _clean_admin(address.get('district') or '')
        if district and slugify(district) != slugify(pick):
            tail = [district, cc]
        elif lvl5:
            tail = [lvl5]            # okres code already embeds the country
        else:
            tail = [iso2 or cc]      # region code / country fallback
    slug = slugify(' '.join([pick] + [t for t in tail if t]))
    return name, (slug or None)


def derive_parent(address: dict):
    """(place_parent_name, place_parent_slug) — the city/area hub a leaf place
    rolls up to (Prosek & Kobylisy -> Praha; villages -> their POÚ-seat town).
    None when there's no city-level container (purely rural). Admin-cleaned, so
    "SO POÚ Říčany" -> "Říčany".
    """
    city = _clean_admin(address.get('city') or address.get('town') or address.get('municipality'))
    if not city:
        return None, None
    cc = (address.get('country_code') or '').lower()
    return city, (slugify(' '.join([city, cc]) if cc else city) or None)


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
        and_(Photo.notes.isnot(None), Photo.notes != ""),
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
            addr = (geo or {}).get('address') or {}
            name, slug = derive_place(addr)
            pname, pslug = derive_parent(addr)
            if opts.dry_run:
                print(f"  {pid} -> {name!r} [{slug}] / parent {pname!r} [{pslug}]", flush=True)
            else:
                await db.execute(update(Photo).where(Photo.id == pid).values(
                    place_name=name, place_slug=slug,
                    place_parent_name=pname, place_parent_slug=pslug))
            changed += 1
        if not opts.dry_run:
            await db.commit()
    print(f"Re-derived {changed} rows.", flush=True)


async def main(opts):
    if opts.rederive:
        return await rederive(opts)
    placed = nocov = errors = 0
    # Keyset pagination by id. Lets us *not* write anything on a transport error
    # (so a transient 503 doesn't strand a photo — a later run retries it) while
    # still advancing past it; with a plain `WHERE geocode IS NULL` the unwritten
    # row would just be re-selected next batch and loop.
    cursor = ''
    async with SessionLocal() as db:
        while opts.limit is None or (placed + nocov) < opts.limit:
            conds = [
                Photo.is_public == True,
                Photo.deleted == False,
                Photo.processing_status == "completed",
                Photo.geometry.isnot(None),
                # Default: rows never written. --retry-no-place also revisits rows
                # left placeless before (out-of-coverage markers) — pair it with a
                # global --geocoder-url.
                Photo.place_slug.is_(None) if opts.retry_no_place else Photo.geocode.is_(None),
                Photo.id > cursor,
            ]
            if opts.filter == 'curated':
                conds.append(_interesting())
            rows = (await db.execute(
                select(Photo.id, ST_Y(Photo.geometry), ST_X(Photo.geometry))
                .where(*conds).order_by(Photo.id).limit(200)
            )).all()
            if not rows:
                break
            for pid, lat, lon in rows:
                cursor = pid
                if opts.limit is not None and (placed + nocov) >= opts.limit:
                    break
                try:
                    geo = reverse_geocode(opts.geocoder_url, lat, lon, opts.zoom, opts.max_km)
                except Exception as e:
                    # Hold off writing on a transport error — leave the row NULL so
                    # a later run retries it.
                    print(f"  {pid} geocode error (left for retry): {e}", flush=True)
                    errors += 1
                    time.sleep(opts.delay)
                    continue
                if geo is None:
                    # Clean response but no usable/near place: out of coverage. Mark
                    # so reruns skip it; revisit later via --retry-no-place + global.
                    nocov += 1
                    if not opts.dry_run:
                        await db.execute(update(Photo).where(Photo.id == pid)
                            .values(geocode={'address': {}, 'display_name': None}))
                else:
                    placed += 1
                    name, slug = derive_place(geo['address'])
                    pname, pslug = derive_parent(geo['address'])
                    if opts.dry_run:
                        print(f"  {lat:.5f},{lon:.5f} -> {name!r} [{slug}] / {pname!r} [{pslug}]", flush=True)
                    else:
                        await db.execute(update(Photo).where(Photo.id == pid).values(
                            geocode=geo, place_name=name, place_slug=slug,
                            place_parent_name=pname, place_parent_slug=pslug))
                if (placed + nocov) % 25 == 0:
                    print(f"  ...{placed} placed, {nocov} no-coverage, {errors} errors", flush=True)
                time.sleep(opts.delay)
            if not opts.dry_run:
                await db.commit()
    print(f"Done: {placed} placed, {nocov} no-coverage, {errors} errors (retriable).", flush=True)


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
                        'coverage-limited instances snapping to a far place; real '
                        'Czech matches observed up to ~2km, foreign snaps 100s of km)')
    p.add_argument('--retry-no-place', action='store_true',
                   help='also re-attempt rows geocoded before but left placeless '
                        '(e.g. out-of-coverage); pair with a global --geocoder-url')
    p.add_argument('--dry-run', action='store_true', help='print, do not write')
    p.add_argument('--rederive', action='store_true',
                   help='recompute place_name/place_slug from stored geocode (no network)')
    asyncio.run(main(p.parse_args()))
