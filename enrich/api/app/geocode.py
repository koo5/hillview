"""Nominatim + Wikipedia lookups with a durable Postgres cache and polite pacing.
Ported from scripts/enrich/resolve_anchors.py (Resolver) — unbounded queries, the
plausibility post-filter moves to the API/UI (computed live from candidate coords
vs the photo's position/bearing, where it's a tunable knob rather than baked-in)."""
import asyncio
import json
import os
import urllib.parse

import httpx
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


async def nominatim_search(query: str) -> list[dict]:
    """→ [{lat, lon, display_name, osm_type, osm_id, type, importance}] (≤8)."""
    hit, cached = await _cached("nominatim", query)
    if hit:
        # error results are cached as a dict {"error": ...} — replay those as "no
        # candidates", never as a candidate list (delete the row to force a retry)
        return cached if isinstance(cached, list) else []
    out = []
    try:
        async with _pace:
            r = await _client.get(f"{NOMINATIM_URL}/search", params={
                "q": query, "format": "jsonv2", "limit": 8,
                "countrycodes": "cz", "accept-language": "cs"})
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
        await _store("nominatim", query, {"error": str(e)[:200]})
        return []
    await _store("nominatim", query, out)
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
