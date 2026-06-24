#!/usr/bin/env python3
"""
Pinpoint annotation texts -> geo coords (design doc: `geocode-fwd`, W1/W2).

The foundational anchor dataset: for every current annotation on the gold panos,
propose a coordinate from (1) body-embedded coords [free], else (2) viewbox-biased
forward geocoding via Nominatim. Output a reviewable HTML + a correctable CSV; the
confirmed coords later become the annotation `location` field (and feed calibration,
eval, bias-calib, training).

Geocoding is a *proposal*, not truth — hence the review flags:
  off-view  : geocoded azimuth is >70 deg off the pano's stored bearing
  far       : >40 km from camera (panoramic tops out ~15-25 km)
  at-camera : <60 m (geocoded onto the camera itself => wrong)

Cache: responses are cached in .geocode_cache.json (content-addressed) so re-runs
don't re-hit the geocoder.

Usage:
  python annotation_geocode.py --data ~/hggg --nominatim https://nominatim.ueueeu.eu
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


def bearing_deg(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def haversine_km(lon1, lat1, lon2, lat2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def ang_norm(d):
    return (d + 180.0) % 360.0 - 180.0


COORD_RE = re.compile(r"(\d{1,2}\.\d{3,})\s*[NnSs]?[,\s]+(\d{1,2}\.\d{3,})\s*[EeWw]?")


def clean_label(body):
    """-> (name|None, (lat,lon)|None, uncertain). Bodies: 'name|place|url|coords'."""
    if not body:
        return None, None, False
    parts = [p.strip() for p in body.split("|")]
    name = parts[0]
    for p in parts:
        m = COORD_RE.search(p)
        if m:
            return name, (float(m.group(1)), float(m.group(2))), False
    uncertain = name.endswith("?") or "(?)" in name
    name = name.rstrip("?").replace("(?)", "").strip()
    if not name or name == "?":
        return None, None, False
    return name, None, uncertain


class Geocoder:
    def __init__(self, base, span, delay, cache_path):
        self.base, self.span, self.delay = base.rstrip("/"), span, delay
        self.cache_path = cache_path
        self.cache = {}
        if os.path.exists(cache_path):
            self.cache = json.load(open(cache_path))
        self.calls = 0

    def save(self):
        json.dump(self.cache, open(self.cache_path, "w"), ensure_ascii=False, indent=0)

    def __call__(self, q, lat, lon):
        key = f"{q}|{lat:.3f},{lon:.3f}|{self.span}"
        if key in self.cache:
            return self.cache[key]
        box = f"{lon - self.span},{lat + self.span},{lon + self.span},{lat - self.span}"
        params = urllib.parse.urlencode({
            "q": q, "format": "jsonv2", "limit": 1, "bounded": 1,
            "viewbox": box, "countrycodes": "cz", "accept-language": "cs"})
        req = urllib.request.Request(self.base + "/search?" + params,
                                     headers={"User-Agent": "hillview-enrich/0.1"})
        res = None
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read())
            if d:
                res = {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]),
                       "display": d[0].get("display_name", "")}
        except Exception as e:
            res = {"error": str(e)[:60]}
        self.cache[key] = res
        self.calls += 1
        if self.calls % 20 == 0:
            self.save()
        time.sleep(self.delay)
        return res


def load_photos(path):
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
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
            out[r["id"]] = {"lon": ll[0], "lat": ll[1], "w": w, "h": h,
                            "ar": max(w, h) / min(w, h) if w and h else 0,
                            "bearing": float(comp) if comp else None,
                            "desc": (r.get("description") or "").strip()}
    return out


def load_annotations(path):
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("is_current") not in ("t", "true", "True", "1"):
                continue
            try:
                geom = (json.loads(row["target"]).get("selector") or {}).get("geometry") or {}
                cx = float(geom["x"]) + float(geom.get("w", 0)) / 2.0
            except Exception:
                cx = None
            out.append({"id": row["id"], "photo_id": row["photo_id"],
                        "body": (row.get("body") or "").strip(), "cx": cx})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--nominatim", default="https://nominatim.ueueeu.eu")
    ap.add_argument("--span", type=float, default=0.3, help="geocode viewbox half-size, deg")
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--min-ar", type=float, default=2.0, help="aspect ratio => pano")
    args = ap.parse_args()

    photos = load_photos(find_csv(args.data, "photos"))
    anns = load_annotations(find_csv(args.data, "photo_annotations"))
    by_photo = {}
    for a in anns:
        by_photo.setdefault(a["photo_id"], []).append(a)
    panos = [pid for pid in by_photo
             if pid in photos and photos[pid]["ar"] >= args.min_ar]
    panos.sort(key=lambda pid: -len(by_photo[pid]))
    print(f"gold panos (annotated, ar>={args.min_ar}): {len(panos)}")

    geo = Geocoder(args.nominatim, args.span, args.delay,
                   os.path.join(HERE, ".geocode_cache.json"))
    records = []
    tally = {"total": 0, "named": 0, "body": 0, "geocoded": 0, "noresult": 0, "flagged": 0}
    for pid in panos:
        p = photos[pid]
        for a in by_photo[pid]:
            tally["total"] += 1
            name, coords, uncertain = clean_label(a["body"])
            rec = {"photo_id": pid, "ann_id": a["id"], "body": a["body"],
                   "name": name or "", "cx": a["cx"], "source": "", "lat": "",
                   "lon": "", "km": "", "az": "", "dbearing": "", "flag": "",
                   "display": "", "uncertain": uncertain}
            if not name:
                rec["source"] = "no-name"
                records.append(rec)
                continue
            tally["named"] += 1
            if coords:
                rec["source"] = "body-coords"
                tally["body"] += 1
            else:
                g = geo(name, p["lat"], p["lon"])
                if not g or "error" in (g or {}) or "lat" not in (g or {}):
                    rec["source"] = "no-result" if g is None or "error" not in g else "geo-error"
                    if g and "error" in g:
                        rec["display"] = g["error"]
                    tally["noresult"] += 1
                    records.append(rec)
                    continue
                coords = (g["lat"], g["lon"])
                rec["display"] = g["display"]
                rec["source"] = "geocoded"
                tally["geocoded"] += 1
            lat, lon = coords
            km = haversine_km(p["lon"], p["lat"], lon, lat)
            az = bearing_deg(p["lon"], p["lat"], lon, lat)
            db = ang_norm(az - p["bearing"]) if p["bearing"] is not None else None
            flags = []
            if km > 40:
                flags.append("far")
            if km < 0.06:
                flags.append("at-camera")
            if db is not None and abs(db) > 70:
                flags.append("off-view")
            rec.update({"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "km": f"{km:.1f}",
                        "az": f"{az:.0f}", "dbearing": f"{db:+.0f}" if db is not None else "",
                        "flag": ",".join(flags)})
            if flags:
                tally["flagged"] += 1
            records.append(rec)
        geo.save()
        loc = sum(1 for r in records if r["photo_id"] == pid and r["lat"])
        print(f"  {pid[:8]}  {len(by_photo[pid]):3} annos  {loc:3} located  "
              f"({photos[pid]['desc'][:40]})")
    geo.save()

    # CSV
    csv_path = os.path.join(HERE, "annotation_geocode.csv")
    cols = ["photo_id", "ann_id", "body", "name", "cx", "source", "lat", "lon",
            "km", "az", "dbearing", "flag", "uncertain", "display"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k, "") for k in cols})

    # HTML
    secs = ""
    for pid in panos:
        p = photos[pid]
        rs = [r for r in records if r["photo_id"] == pid]
        loc = sum(1 for r in rs if r["lat"])
        trs = ""
        for r in sorted(rs, key=lambda r: (r["cx"] is None, r["cx"] or 0)):
            color = "#070" if r["source"] in ("body-coords",) else "#000"
            if r["flag"]:
                color = "#c00"
            elif not r["lat"]:
                color = "#999"
            maplink = (f'<a href="https://www.openstreetmap.org/?mlat={r["lat"]}&mlon={r["lon"]}'
                       f'&zoom=16" target=_blank>map</a>' if r["lat"] else "")
            trs += (f'<tr style="color:{color}"><td>{html.escape(r["body"][:46])}'
                    f'{"?" if r["uncertain"] else ""}</td>'
                    f'<td>{r["cx"]:.3f}</td>' if r["cx"] is not None else
                    f'<tr style="color:{color}"><td>{html.escape(r["body"][:46])}</td><td>-</td>')
            trs += (f'<td>{r["source"]}</td><td>{r["lat"]}{("," + r["lon"]) if r["lon"] else ""}</td>'
                    f'<td>{r["km"]}</td><td>{r["az"]}</td><td>{r["dbearing"]}</td>'
                    f'<td><b>{r["flag"]}</b></td><td>{maplink}</td></tr>')
        secs += (f'<h3>{pid[:8]} — {html.escape(p["desc"][:60])} '
                 f'<small>({loc}/{len(rs)} located · cam {p["lat"]:.4f},{p["lon"]:.4f} · '
                 f'bearing {p["bearing"]})</small></h3>'
                 f'<table><tr><th>label</th><th>x</th><th>source</th><th>coords</th>'
                 f'<th>km</th><th>az</th><th>Δbrg</th><th>flag</th><th></th></tr>{trs}</table>')
    htmldoc = f"""<!doctype html><meta charset=utf-8><title>annotation geocoding</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1000px}}
td,th{{padding:2px 8px;border-bottom:1px solid #eee;font-size:12px;text-align:left}}
h3{{margin-top:26px}}</style>
<h2>Annotation → geo coords (proposals for review)</h2>
<p>{tally['total']} annotations on {len(panos)} panos · named {tally['named']} ·
body-coords {tally['body']} · geocoded {tally['geocoded']} · no-result {tally['noresult']} ·
<b style=color:#c00>flagged {tally['flagged']}</b></p>
<p style=color:#888>Green = free body coords. Red = flagged (off-view / far / at-camera) —
likely wrong geocode or a very biased pano bearing; review these. Grey = not located.
Δbrg = geocoded azimuth minus the pano's stored bearing.</p>
{secs}"""
    html_path = os.path.join(HERE, "annotation_geocode.html")
    open(html_path, "w").write(htmldoc)

    print(f"\n{tally}")
    print(f"CSV : {csv_path}")
    print(f"HTML: {html_path}")


if __name__ == "__main__":
    main()
