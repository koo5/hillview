#!/usr/bin/env python3
"""
resolve_anchors — v2 of annotation -> geo coords (supersedes annotation_geocode.py).

Improvements over v1 (per field notes 2026-06-15):
  * ignore `oops` annotations (stitching-error markers)
  * body Wikipedia URL -> trust its coords (Wikipedia coordinates API)   [high conf]
  * UNBOUNDED geocode + bearing/distance POST-FILTER instead of a hard bbox
    (the bbox clipped distant POIs e.g. Jested; post-filter also disambiguates
    wrong-instance hits like the 150 km "Vysehrad"). Unbounded queries are
    camera-independent => cached & deduped by name.
  * append the 2nd `|` segment as context when the bare name finds nothing
  (deferred: query relaxation / simplification — Czech-declension fiddly)

Resolution order per label: body-coords -> wikipedia -> geocode(name) ->
geocode(name + context). Each candidate scored by in-view (bearing+distance vs the
pano); we always keep the best guess and FLAG the uncertain ones for review.

Usage:
  python resolve_anchors.py --data ~/hggg --nominatim https://nominatim.ueueeu.eu
"""
import argparse
import csv
import glob
import html
import json
import math
import os
import re
import struct
import sys
import time
import urllib.parse
import urllib.request

csv.field_size_limit(sys.maxsize)
HERE = os.path.dirname(os.path.abspath(__file__))

COORD_RE = re.compile(r"(\d{1,2}\.\d{3,})\s*[NnSs]?[,\s]+(\d{1,2}\.\d{3,})\s*[EeWw]?")
WIKI_RE = re.compile(r"https?://(\w{2,3})\.wikipedia\.org/wiki/([^\s|)]+)")
URL_RE = re.compile(r"https?://")
TOL_DEG = 90.0     # post-filter: bearing half-window (permissive; rejects wrong-direction)
PEAK_KM = 150.0    # natural features (peaks/hills) are legitimately far in a panorama
NEAR_KM = 40.0     # buildings/places should be near-ish; far => probably wrong instance


def kind_ceiling(c):
    t = c.get("type", "")
    return PEAK_KM if any(k in t for k in
                          ("peak", "hill", "volcano", "ridge", "massif", "natural")) else NEAR_KM


def find_csv(d, prefix):
    hits = sorted(glob.glob(os.path.join(d, prefix + "*.csv")))
    if not hits:
        raise FileNotFoundError(f"no {prefix}*.csv in {d}")
    return hits[-1]


def parse_point(g):
    if not g:
        return None
    g = g.strip()
    if g.upper().startswith("POINT"):
        try:
            lon, lat = g[g.index("(") + 1:g.index(")")].split()
            return float(lon), float(lat)
        except Exception:
            return None
    try:
        if g.lower().startswith("0101000020"):
            b = bytes.fromhex(g)
            return struct.unpack_from("<d", b, 9)[0], struct.unpack_from("<d", b, 17)[0]
    except Exception:
        pass
    return None


def bearing_deg(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def haversine_km(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def ang_norm(d):
    return (d + 180.0) % 360.0 - 180.0


def parse_body(body):
    """-> dict(name, body_coords, wiki(lang,title), context) | None if skip."""
    if not body:
        return None
    parts = [p.strip() for p in body.split("|")]
    name0 = parts[0]
    if name0.lower() == "oops" or body.lower().startswith("oops"):
        return None
    coords = ctx = wiki = None
    for p in parts:
        m = COORD_RE.search(p)
        if m and not coords:
            coords = (float(m.group(1)), float(m.group(2)))
        w = WIKI_RE.search(p)
        if w and not wiki:
            wiki = (w.group(1), urllib.parse.unquote(w.group(2)).replace("_", " "))
    if len(parts) > 1 and not URL_RE.search(parts[1]) and not COORD_RE.search(parts[1]):
        ctx = parts[1]
    name = name0.rstrip("?").replace("(?)", "").strip()
    if not name or name == "?":
        return None
    return {"name": name, "coords": coords, "wiki": wiki, "ctx": ctx,
            "uncertain": name0.endswith("?") or "(?)" in name0}


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "hillview-enrich/0.2"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


class Resolver:
    def __init__(self, base, delay):
        self.base, self.delay = base.rstrip("/"), delay
        self.gc = self._load(".anchor_geocode_cache.json")
        self.wc = self._load(".anchor_wiki_cache.json")
        self.calls = 0

    def _load(self, n):
        p = os.path.join(HERE, n)
        return json.load(open(p)) if os.path.exists(p) else {}

    def save(self):
        json.dump(self.gc, open(os.path.join(HERE, ".anchor_geocode_cache.json"), "w"), ensure_ascii=False)
        json.dump(self.wc, open(os.path.join(HERE, ".anchor_wiki_cache.json"), "w"), ensure_ascii=False)

    def _tick(self):
        self.calls += 1
        if self.calls % 20 == 0:
            self.save()
        time.sleep(self.delay)

    def wiki(self, lang, title):
        key = f"{lang}:{title}"
        if key in self.wc:
            return self.wc[key]
        q = urllib.parse.urlencode({"action": "query", "prop": "coordinates",
                                    "titles": title, "format": "json"})
        res = None
        try:
            d = http_json(f"https://{lang}.wikipedia.org/w/api.php?{q}")
            for pg in (d.get("query", {}).get("pages", {}) or {}).values():
                c = (pg.get("coordinates") or [None])[0]
                if c:
                    res = [c["lat"], c["lon"]]
        except Exception:
            res = None
        self.wc[key] = res
        self._tick()
        return res

    def geocode(self, q):
        """unbounded, cz; cached by query string (camera-independent)."""
        if q in self.gc:
            return self.gc[q]
        params = urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 8,
                                         "countrycodes": "cz", "accept-language": "cs"})
        out = []
        try:
            for d in http_json(f"{self.base}/search?{params}"):
                out.append({"lat": float(d["lat"]), "lon": float(d["lon"]),
                            "imp": float(d.get("importance", 0) or 0),
                            "disp": d.get("display_name", "")[:70],
                            "type": f"{d.get('category', d.get('class',''))}/{d.get('type','')}"})
        except Exception as e:
            out = [{"error": str(e)[:60]}]
        self.gc[q] = out
        self._tick()
        return out


def pick(cands, cam):
    """choose best candidate for a camera; -> (cand|None, km, db, flag)."""
    cands = [c for c in cands if "lat" in c]
    if not cands:
        return None, None, None, "no-result"
    scored = []
    for c in cands:
        km = haversine_km(cam["lon"], cam["lat"], c["lon"], c["lat"])
        db = ang_norm(bearing_deg(cam["lon"], cam["lat"], c["lon"], c["lat"]) - cam["bearing"]) \
            if cam["bearing"] is not None else None
        iv = db is not None and abs(db) <= TOL_DEG and 0.2 <= km <= kind_ceiling(c)
        scored.append((c, km, db, iv))
    inview = [s for s in scored if s[3]]
    pool = inview or scored
    c, km, db, iv = max(pool, key=lambda s: s[0]["imp"])
    flag = ""
    if not iv:
        flag = "off-view" if (db is not None and abs(db) > TOL_DEG) else "far"
    elif km < 0.2:
        flag = "at-camera"
    return c, km, db, flag


def load_photos(path):
    out = {}
    for r in csv.DictReader(open(path)):
        if r.get("deleted") in ("t", "true", "True", "1"):
            continue
        ll = parse_point(r.get("geometry"))
        if not ll:
            continue
        try:
            w, h = int(r["width"]), int(r["height"])
        except Exception:
            continue
        comp = r.get("compass_angle")
        out[r["id"]] = {"lon": ll[0], "lat": ll[1], "ar": max(w, h) / min(w, h) if w and h else 0,
                        "bearing": float(comp) if comp else None,
                        "desc": (r.get("description") or "").strip()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--nominatim", default="https://nominatim.ueueeu.eu")
    ap.add_argument("--delay", type=float, default=0.12)
    ap.add_argument("--min-ar", type=float, default=2.0)
    args = ap.parse_args()

    photos = load_photos(find_csv(args.data, "photos"))
    by_photo = {}
    for row in csv.DictReader(open(find_csv(args.data, "photo_annotations"))):
        if row.get("is_current") in ("t", "true", "True", "1"):
            by_photo.setdefault(row["photo_id"], []).append(
                {"id": row["id"], "body": (row.get("body") or "").strip()})
    panos = sorted([p for p in by_photo if p in photos and photos[p]["ar"] >= args.min_ar],
                   key=lambda p: -len(by_photo[p]))

    rv = Resolver(args.nominatim, args.delay)
    recs = []
    st = {"total": 0, "oops": 0, "noname": 0, "body": 0, "wiki": 0, "geo": 0,
          "geo_ctx": 0, "noresult": 0, "flagged": 0}
    for pid in panos:
        cam = photos[pid]
        for a in by_photo[pid]:
            st["total"] += 1
            pb = parse_body(a["body"])
            rec = {"photo_id": pid, "ann_id": a["id"], "body": a["body"],
                   "source": "", "lat": "", "lon": "", "km": "", "db": "", "flag": "", "disp": ""}
            if pb is None:
                rec["source"] = "oops" if (a["body"].lower().startswith("oops")) else "no-name"
                st["oops" if rec["source"] == "oops" else "noname"] += 1
                recs.append(rec)
                continue
            coords = None
            src = ""
            if pb["coords"]:
                coords, src = pb["coords"], "body-coords"
                st["body"] += 1
            elif pb["wiki"] and rv.wiki(*pb["wiki"]):
                coords, src = rv.wiki(*pb["wiki"]), "wikipedia"
                st["wiki"] += 1
            if coords:
                km = haversine_km(cam["lon"], cam["lat"], coords[1], coords[0])
                db = ang_norm(bearing_deg(cam["lon"], cam["lat"], coords[1], coords[0]) - cam["bearing"]) \
                    if cam["bearing"] is not None else None
                rec.update(source=src, lat=f"{coords[0]:.5f}", lon=f"{coords[1]:.5f}",
                           km=f"{km:.1f}", db=f"{db:+.0f}" if db is not None else "")
                recs.append(rec)
                continue
            # geocode (name, then name+context)
            c, km, db, flag = pick(rv.geocode(pb["name"]), cam)
            used = "geocoded"
            if (c is None or flag) and pb["ctx"]:
                c2, km2, db2, flag2 = pick(rv.geocode(f"{pb['name']} {pb['ctx']}"), cam)
                if c2 is not None and (c is None or (flag and not flag2)):
                    c, km, db, flag, used = c2, km2, db2, flag2, "geocoded-ctx"
            if c is None:
                rec["source"] = "no-result"
                st["noresult"] += 1
            else:
                st["geo_ctx" if used == "geocoded-ctx" else "geo"] += 1
                if flag:
                    st["flagged"] += 1
                rec.update(source=used, lat=f"{c['lat']:.5f}", lon=f"{c['lon']:.5f}",
                           km=f"{km:.1f}", db=f"{db:+.0f}" if db is not None else "",
                           flag=flag, disp=c["disp"])
            recs.append(rec)
        rv.save()
        loc = sum(1 for r in recs if r["photo_id"] == pid and r["lat"])
        print(f"  {pid[:8]} {len(by_photo[pid]):3} annos  {loc:3} located  ({cam['desc'][:38]})")
    rv.save()

    located = sum(1 for r in recs if r["lat"])
    clean = sum(1 for r in recs if r["lat"] and not r["flag"])
    with open(os.path.join(HERE, "annotation_anchors.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["photo_id", "ann_id", "body", "source",
                                          "lat", "lon", "km", "db", "flag", "disp"])
        w.writeheader()
        for r in recs:
            w.writerow(r)

    secs = ""
    for pid in panos:
        cam = photos[pid]
        rs = [r for r in recs if r["photo_id"] == pid]
        trs = ""
        for r in rs:
            if r["source"] in ("no-name", "oops"):
                continue                       # collapse '?' / stitching markers into the header count
            col = {"body-coords": "#070", "wikipedia": "#06c"}.get(r["source"], "#000")
            if r["flag"]:
                col = "#c00"
            elif not r["lat"]:
                col = "#999"
            ml = (f'<a href="https://www.openstreetmap.org/?mlat={r["lat"]}&mlon={r["lon"]}&zoom=16" target=_blank>map</a>'
                  if r["lat"] else "")
            trs += (f'<tr style=color:{col}><td>{html.escape(r["body"][:46])}</td>'
                    f'<td>{r["source"]}</td><td>{r["lat"]}{("," + r["lon"]) if r["lon"] else ""}</td>'
                    f'<td>{r["km"]}</td><td>{r["db"]}</td><td><b>{r["flag"]}</b></td>'
                    f'<td>{html.escape(r["disp"][:42])}</td><td>{ml}</td></tr>')
        loc = sum(1 for r in rs if r["lat"])
        nq = sum(1 for r in rs if r["source"] == "no-name")
        noops = sum(1 for r in rs if r["source"] == "oops")
        secs += (f'<h3>{pid[:8]} — {html.escape(cam["desc"][:55])} '
                 f'<small>({loc} located · {nq} unidentified(?) · {noops} oops · '
                 f'bearing {cam["bearing"]})</small></h3>'
                 f'<table><tr><th>label</th><th>source</th><th>coords</th><th>km</th>'
                 f'<th>Δbrg</th><th>flag</th><th>nominatim/wiki</th><th></th></tr>{trs}</table>')
    doc = f"""<!doctype html><meta charset=utf-8><title>anchors v2</title>
<style>body{{font:13px system-ui;margin:24px;max-width:1000px}}
td,th{{padding:2px 8px;border-bottom:1px solid #eee;font-size:12px;text-align:left}}h3{{margin-top:22px}}</style>
<h2>Annotation anchors v2 (unbounded + post-filter, wiki, no-oops)</h2>
<p>{st['total']} annos · located <b>{located}</b> (clean {clean}, flagged {st['flagged']}) ·
body-coords {st['body']} · wiki {st['wiki']} · geocoded {st['geo']} · via-context {st['geo_ctx']} ·
no-result {st['noresult']} · no-name {st['noname']} · oops {st['oops']}</p>
<p style=color:#888>blue=wikipedia, green=body-coords, red=flagged, grey=unresolved.
<b>v1 was 244 located / ~215 clean.</b></p>
{secs}"""
    open(os.path.join(HERE, "annotation_anchors.html"), "w").write(doc)
    print(f"\n{st}\nlocated={located} clean={clean}")
    print("CSV : scripts/enrich/annotation_anchors.csv\nHTML: scripts/enrich/annotation_anchors.html")


if __name__ == "__main__":
    main()
