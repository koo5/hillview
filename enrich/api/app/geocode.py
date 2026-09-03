"""Nominatim + Wikipedia lookups with a durable Postgres cache and polite pacing.
Ported from scripts/enrich/resolve_anchors.py (Resolver) — unbounded queries, the
plausibility post-filter moves to the API/UI (computed live from candidate coords
vs the photo's position/bearing, where it's a tunable knob rather than baked-in)."""
import asyncio
import json
import os
import urllib.parse

import httpx
import re
import math
from sqlalchemy import text

from .db import wb_engine

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.ueueeu.eu").rstrip("/")
LOOKUP_DELAY = float(os.getenv("GEOCODE_DELAY", "0.7"))   # seconds between remote calls

_client = httpx.AsyncClient(timeout=25, headers={"User-Agent": "hillview-enrich/0.3"})
_pace = asyncio.Lock()


async def _cached(kind: str, query: str):
    async with wb_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT result FROM geocode_cache WHERE kind = :k AND query = :q"),
            {"k": kind, "q": query})).first()
    return (True, row[0]) if row else (False, None)


async def _store(kind: str, query: str, result) -> None:
    async with wb_engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO geocode_cache (kind, query, result) "
            "VALUES (:k, :q, CAST(:r AS jsonb)) "
            "ON CONFLICT (kind, query) DO UPDATE SET result = EXCLUDED.result, "
            "fetched_at = now()"),
            {"k": kind, "q": query, "r": json.dumps(result)})


# viewbox bias: prefer hits inside a box of ±VIEWBOX_LAT° / ±VIEWBOX_LON° (≈ ±110 km)
# around the photo, snapped to a 0.5° grid so nearby photos share cache rows.
# bounded=0 → hits outside still come back, just ranked lower.
VIEWBOX_LAT, VIEWBOX_LON = 1.0, 1.5


def viewbox_for(lat: float, lon: float) -> tuple[str, str]:
    """→ (cache suffix, nominatim viewbox 'x1,y1,x2,y2') for a photo position."""
    clat, clon = round(lat * 2) / 2, round(lon * 2) / 2
    return (f"@{clat},{clon}",
            f"{clon - VIEWBOX_LON},{clat + VIEWBOX_LAT},{clon + VIEWBOX_LON},{clat - VIEWBOX_LAT}")


async def nominatim_search(query: str, near: tuple[float, float] | None = None) -> list[dict]:
    """→ [{lat, lon, display_name, osm_type, osm_id, type, importance}] (≤8).
    `near` = the photo's (lat, lon): results inside the viewbox around it rank
    first (namesakes 90 km away stop winning on importance alone)."""
    suffix, viewbox = viewbox_for(*near) if near else ("", None)
    hit, cached = await _cached("nominatim", query + suffix)
    if hit:
        # error results are cached as a dict {"error": ...} — replay those as "no
        # candidates", never as a candidate list (delete the row to force a retry)
        return cached if isinstance(cached, list) else []
    out = []
    try:
        async with _pace:
            params = {"q": query, "format": "jsonv2", "limit": 8,
                      "countrycodes": "cz", "accept-language": "cs"}
            if viewbox:
                params.update({"viewbox": viewbox, "bounded": 0})
            r = await _client.get(f"{NOMINATIM_URL}/search", params=params)
            await asyncio.sleep(LOOKUP_DELAY)
        r.raise_for_status()
        for d in r.json():
            if not (d.get("osm_type") and d.get("osm_id")):
                continue
            out.append({
                "lat": float(d["lat"]), "lon": float(d["lon"]),
                "display_name": d.get("display_name", ""),
                "osm_type": d["osm_type"], "osm_id": int(d["osm_id"]),
                "type": f"{d.get('category', d.get('class', ''))}/{d.get('type', '')}",
                "importance": float(d.get("importance") or 0),
            })
    except Exception as e:
        # cache failures as empty so a flaky call doesn't wedge re-runs; the cache
        # row's fetched_at shows when, and deleting the row retries.
        await _store("nominatim", query + suffix, {"error": str(e)[:200]})
        return []
    await _store("nominatim", query + suffix, out)
    return out


def parse_wikipedia_url(url: str) -> tuple[str, str, str, str]:
    """→ (lang, raw_title, canonical_url, label). Raises ValueError on non-wiki
    URLs. NOT parser.WIKI_RE — that charset excludes ')' (annotation bodies wrap
    URLs in parens), truncating titles like Bezděz_(hrad). Normalizes mobile
    hosts (cs.m.wikipedia.org) from phone pastes."""
    import re as _re
    import urllib.parse as _up
    u = _up.urlsplit(url.strip())
    hm = _re.fullmatch(r"(\w{2,3})(?:\.m)?\.wikipedia\.org", u.netloc)
    if not hm or not u.path.startswith("/wiki/"):
        raise ValueError("not a wikipedia URL (need https://xx.wikipedia.org/wiki/Title)")
    lang = hm.group(1)
    raw_title = u.path[len("/wiki/"):]
    label = _up.unquote(raw_title).replace("_", " ")
    return lang, raw_title, f"https://{lang}.wikipedia.org/wiki/{raw_title}", label


async def wikipedia_coords(lang: str, title: str) -> dict | None:
    """→ {lat, lon} | None."""
    key = f"{lang}:{title}"
    hit, cached = await _cached("wikipedia", key)
    if hit:
        return cached if cached and "lat" in cached else None
    res = None
    try:
        async with _pace:
            r = await _client.get(f"https://{lang}.wikipedia.org/w/api.php", params={
                "action": "query", "prop": "coordinates", "titles": title,
                "format": "json"})
            await asyncio.sleep(LOOKUP_DELAY)
        r.raise_for_status()
        for pg in (r.json().get("query", {}).get("pages", {}) or {}).values():
            c = (pg.get("coordinates") or [None])[0]
            if c:
                res = {"lat": c["lat"], "lon": c["lon"]}
        if res is None:
            # some wikis' infoboxes never register with the GeoData extension
            # (e.g. cs: Žižkovská televizní věž); the REST summary pulls the
            # Wikidata coordinate and follows redirects.
            async with _pace:
                r2 = await _client.get(
                    f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
                    + urllib.parse.quote(title.replace(" ", "_"), safe=""))
                await asyncio.sleep(LOOKUP_DELAY)
            if r2.status_code == 200:
                c = r2.json().get("coordinates")
                if c:
                    res = {"lat": c["lat"], "lon": c["lon"]}
    except Exception as e:
        await _store("wikipedia", key, {"error": str(e)[:200]})
        return None
    await _store("wikipedia", key, res or {})
    return res


def osm_uri(osm_type: str, osm_id: int) -> str:
    return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"


# ---------------------------------------------------------------------------
# Observer height from OSM: a lookout tower / mast / viewpoint with a height
# tag within a few tens of metres of the viewpoint — the default eye height for
# terrain renders (the phone's GPS altitude is not to be trusted for this).
# ---------------------------------------------------------------------------
OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OBSERVER_RADIUS_M = float(os.getenv("OBSERVER_RADIUS_M", "40"))


def parse_height_m(value) -> float | None:
    """OSM height tag → metres: '25', '25 m', '25.5m', '80 ft', "80'"; None otherwise."""
    if value is None:
        return None
    s = str(value).strip().lower().replace(",", ".")
    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*(m|meters?|metres?|ft|feet|')?$", s)
    if not m:
        return None
    v = float(m.group(1))
    unit = m.group(2) or "m"
    return round(v * 0.3048, 2) if unit in ("ft", "feet", "'") else v


WIKIDATA_M_PER_UNIT = {"Q11573": 1.0, "Q3710": 0.3048, "Q174728": 0.01}   # metre, foot, centimetre


async def wikidata_height_m(qid: str) -> float | None:
    """Wikidata P2048 (height) of an entity in metres, cached (kind 'wikidata_height')."""
    hit, cached = await _cached("wikidata_height", qid)
    if hit:
        return cached.get("height_m") if isinstance(cached, dict) else None
    res: dict = {}
    try:
        async with _pace:
            r = await _client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
            await asyncio.sleep(LOOKUP_DELAY)
        r.raise_for_status()
        claims = r.json()["entities"][qid]["claims"].get("P2048", [])
        for cl in claims:
            v = cl.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            unit = str(v.get("unit", "")).rsplit("/", 1)[-1]
            if "amount" in v and unit in WIKIDATA_M_PER_UNIT:
                res = {"height_m": round(float(v["amount"]) * WIKIDATA_M_PER_UNIT[unit], 2)}
                break
    except Exception as e:
        await _store("wikidata_height", qid, {"error": str(e)[:200]})
        return None
    await _store("wikidata_height", qid, res)
    return res.get("height_m")


async def osm_observer_height(lat: float, lon: float,
                              radius_m: float = OBSERVER_RADIUS_M) -> dict | None:
    """Nearest OSM tower / mast / viewpoint within radius_m of (lat, lon) →
    {height_m, height_source, name, kind, distance_m, osm} | None. height_m
    from the OSM height tag, else from the object's wikidata entity (P2048),
    else None — the structure is still reported so the bench can ask for a
    pinned height. Cached per 5-dp position (geocode_cache kind 'osm_height')."""
    key = f"{lat:.5f},{lon:.5f}@{radius_m:.0f}"
    hit, cached = await _cached("osm_height", key)
    if hit:
        return cached if cached and "osm" in cached else None
    q = (f'[out:json][timeout:20];('
         f'nwr["man_made"~"^(tower|observation_tower|mast|communications_tower)$"](around:{radius_m},{lat},{lon});'
         f'nwr["tourism"="viewpoint"](around:{radius_m},{lat},{lon});'
         f'nwr["building"="tower"](around:{radius_m},{lat},{lon});'
         f');out center tags;')
    res = None
    try:
        async with _pace:
            r = await _client.post(OVERPASS_URL, data={"data": q})
            await asyncio.sleep(LOOKUP_DELAY)
        r.raise_for_status()
        cands = []
        for e in r.json().get("elements", []):
            t = e.get("tags", {})
            elat, elon = (e.get("lat"), e.get("lon")) if "lat" in e else (
                e.get("center", {}).get("lat"), e.get("center", {}).get("lon"))
            if elat is None:
                continue
            d = math.hypot((elat - lat) * 111_320, (elon - lon) * 111_320 * math.cos(math.radians(lat)))
            h, src = parse_height_m(t.get("height")), "osm height tag"
            if h is None and t.get("wikidata"):
                h = await wikidata_height_m(t["wikidata"])
                src = f"wikidata {t['wikidata']} P2048" if h is not None else None
            cands.append({"height_m": h, "height_source": src if h is not None else None,
                          "name": t.get("name"),
                          "kind": t.get("man_made") or t.get("tourism") or t.get("building"),
                          "distance_m": round(d, 1), "osm": f"{e['type']}/{e['id']}",
                          "wikidata": t.get("wikidata")})
        # nearest one that has a height; else the nearest structure at all
        with_h = [c for c in cands if c["height_m"] is not None]
        pool = with_h or cands
        res = min(pool, key=lambda c: c["distance_m"]) if pool else None
    except Exception as e:
        await _store("osm_height", key, {"error": str(e)[:200]})
        return None
    await _store("osm_height", key, res or {})
    return res
