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


def _is_admin_label(s):
    """Whether a Nominatim value names an administrative unit rather than a
    place. Czech data puts these in the same fields as real names — Prague's
    `suburb` is the správní obvod ("SO Praha 10") while the neighbourhood
    ("Spořilov") sits in `quarter`. Stripping the prefix hides that: it turns
    the unit into something that reads like a place name, so it has to be
    detected before cleaning, not after."""
    return bool(s) and bool(_ADMIN_PREFIX.match(s))


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
    # Field order is granularity, finest first — but a field holding an
    # administrative unit loses to any field holding a real name, however much
    # coarser. Without that, a Spořilov photo (quarter=Spořilov, suburb=SO
    # Praha 10, borough=Praha 4) came out as "Praha 10", which is both an admin
    # artifact and locally wrong: Spořilov belongs to Praha 4.
    # An administrative unit is a worse answer than a named place, but a better
    # one than giving up and naming the whole city: "SO Praha 9" beats "Praha"
    # when the address offers nothing finer. Hence three tiers rather than a
    # plain preference order — sorting only by granularity picked "Praha 10" for
    # a Spořilov photo, and sorting only by non-adminness demoted "Praha 9" all
    # the way to "Praha".
    fine = [address.get(k) for k in (
        'neighbourhood', 'suburb', 'quarter', 'village', 'town', 'borough', 'city_district')]
    coarse = [address.get(k) for k in ('municipality', 'city', 'county')]
    pick = _clean_admin(
        next((c for c in fine if c and not _is_admin_label(c)), None)
        or next((c for c in fine if c), None)
        or next((c for c in coarse if c), None)
    )
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
    # Progress cadence follows the cost of a request. A summary every 25 rows is
    # fine at sub-second delays, but a politeness-limited pass against a public
    # instance spends minutes per row — 25 of them is hours of total silence, in
    # which a working container is indistinguishable from a wedged one. Slow
    # passes therefore narrate every row.
    log_every = 1 if opts.delay >= 30 else 25
    # Banner, so `docker logs` shows immediately which endpoint and which half of
    # the work this container is doing — the two services differ only in env.
    scope = 'previously unresolved (no coverage)' if opts.retry_no_place else 'not yet geocoded'
    print(f"Pass: {scope}, filter={opts.filter}, geocoder={opts.geocoder_url}, "
          f"delay={opts.delay}s", flush=True)
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
                # Default: rows never tried. --retry-no-place takes the complement
                # — rows a previous run DID resolve a response for but found no
                # usable place in (the out-of-coverage marker written below), and
                # only those. The two sets are disjoint on purpose: the retry pass
                # is meant to run against a different, wider geocoder, and if it
                # also swept up never-tried rows it would send the whole remaining
                # backlog there instead of just the tail its instance is needed
                # for. (Merely `place_slug IS NULL` is that superset.)
                and_(Photo.geocode.isnot(None), Photo.place_slug.is_(None))
                if opts.retry_no_place else Photo.geocode.is_(None),
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
                    if opts.dry_run or log_every == 1:
                        print(f"  {lat:.5f},{lon:.5f} -> {name!r} [{slug}] / {pname!r} [{pslug}]", flush=True)
                    if not opts.dry_run:
                        await db.execute(update(Photo).where(Photo.id == pid).values(
                            geocode=geo, place_name=name, place_slug=slug,
                            place_parent_name=pname, place_parent_slug=pslug))
                if (placed + nocov) % log_every == 0:
                    print(f"  ...{placed} placed, {nocov} no-coverage, {errors} errors", flush=True)
                time.sleep(opts.delay)
            if not opts.dry_run:
                await db.commit()
    print(f"Done: {placed} placed, {nocov} no-coverage, {errors} errors (retriable).", flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    # Defaults from the environment so the container needs no argv: NOMINATIM_URL
    # is the same variable the enrichment workbench uses (enrich/api/app/geocode.py),
    # so one setting points both at the self-hosted instance.
    p.add_argument('--geocoder-url',
                   default=os.getenv('NOMINATIM_URL', 'https://nominatim.openstreetmap.org'),
                   help='Nominatim-compatible base URL (self-host for bulk!); '
                        'defaults to $NOMINATIM_URL')
    p.add_argument('--filter', choices=['all', 'curated', 'curated-first'],
                   default=os.getenv('BACKFILL_PLACES_FILTER', 'all'),
                   help="'curated' = only the interesting set (panos etc.) for "
                        "validation; 'curated-first' = that set, then everything "
                        "else. The main scan walks photos in id order, i.e. upload "
                        "order, so without this the photos whose place_name is "
                        "actually read (the /bestof and /activity headings) are "
                        "scattered through a many-hour run. Defaults to "
                        "$BACKFILL_PLACES_FILTER")
    p.add_argument('--limit', type=int, default=None, help='max photos this run')
    p.add_argument('--delay', type=float, default=1.1, help='seconds between requests')
    p.add_argument('--zoom', type=int, default=16, help='Nominatim zoom (granularity)')
    p.add_argument('--max-km', type=float, default=5.0,
                   help='reject matches farther than this from the photo (guards '
                        'coverage-limited instances snapping to a far place; real '
                        'Czech matches observed up to ~2km, foreign snaps 100s of km)')
    p.add_argument('--retry-no-place', action='store_true',
                   default=os.getenv('BACKFILL_PLACES_RETRY_NO_PLACE', '').lower() in ('1', 'true', 'yes'),
                   help='ONLY re-attempt rows a previous run left placeless '
                        '(out-of-coverage); pair with a wider --geocoder-url. '
                        'Never-tried rows are left to the default pass. '
                        'Defaults to $BACKFILL_PLACES_RETRY_NO_PLACE')
    p.add_argument('--dry-run', action='store_true', help='print, do not write')
    p.add_argument('--rederive', action='store_true',
                   help='recompute place_name/place_slug from stored geocode (no network)')
    p.add_argument('--loop-interval', type=float,
                   default=float(os.getenv('BACKFILL_PLACES_INTERVAL', '0')),
                   help='keep running: sleep this many seconds after each pass and '
                        'start over (0 = single pass, the default). Photos keep '
                        'arriving, so the containerised deployment loops; a pass '
                        'with nothing left to do costs one indexed query. '
                        'Defaults to $BACKFILL_PLACES_INTERVAL')
    opts = p.parse_args()

    async def run_forever():
        # 'curated-first' is two ordinary passes: the interesting set drains first,
        # so a fresh deployment gets readable headings within minutes instead of
        # hours. Each pass is resumable on its own — correct across restarts.
        passes = ['curated', 'all'] if opts.filter == 'curated-first' else [opts.filter]
        while True:
            for f in passes:
                await main(argparse.Namespace(**{**vars(opts), 'filter': f}))
            if not opts.loop_interval or opts.loop_interval <= 0:
                return
            # Transport errors leave their rows NULL, so the next pass retries them.
            print(f"Sleeping {opts.loop_interval:.0f}s before the next pass.", flush=True)
            await asyncio.sleep(opts.loop_interval)

    # One event loop for the whole process: SessionLocal's pool binds to the loop
    # that first used it, so a second asyncio.run() (a second pass, or the next
    # interval) would fail with "attached to a different loop".
    asyncio.run(run_forever())
