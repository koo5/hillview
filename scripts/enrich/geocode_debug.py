#!/usr/bin/env python3
"""
Geocoding-debug report — for tuning the lookup logic.

For every annotation that goes through Nominatim (named, no body-coords), re-query
with limit=8 + rich fields and show, per query:
  * the full annotation body and the searched string (after clean_label)
  * the candidate list Nominatim returned (display_name, class/type, importance,
    place_rank, coords, km from camera, Δ vs pano bearing, in-view?)
  * a diagnosis: which candidate the current top-1 logic picks, and whether a
    LOWER-ranked candidate is a better fit (=> re-ranking by bearing/distance would
    help) — or whether it's a no-result / no-good-candidate.

Anchors: TOC links to each pano section and each annotation row.

Cache: .geocode_debug_cache.json (separate from the top-1 cache). Re-runs are free.

Usage:
  python geocode_debug.py --data ~/hggg --nominatim https://nominatim.ueueeu.eu
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
    if not body:
        return None, True
    parts = [p.strip() for p in body.split("|")]
    name = parts[0]
    for p in parts:
        if COORD_RE.search(p):
            return None, False           # has body-coords -> not a Nominatim query
    uncertain = name.endswith("?") or "(?)" in name
    name = name.rstrip("?").replace("(?)", "").strip()
    if not name or name == "?":
        return None, False
    return name, uncertain


def in_view(km, dbrg):
    return (dbrg is not None and abs(dbrg) <= 60) and (0.2 <= km <= 35)


class Debugger:
    def __init__(self, base, span, delay, limit, cache_path):
        self.base, self.span, self.delay, self.limit = base.rstrip("/"), span, delay, limit
        self.cache_path = cache_path
        self.cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
        self.calls = 0

    def save(self):
        json.dump(self.cache, open(self.cache_path, "w"), ensure_ascii=False)

    def query(self, q, lat, lon):
        key = f"{q}|{lat:.3f},{lon:.3f}|{self.span}|{self.limit}"
        if key in self.cache:
            return self.cache[key]
        box = f"{lon - self.span},{lat + self.span},{lon + self.span},{lat - self.span}"
        params = urllib.parse.urlencode({
            "q": q, "format": "jsonv2", "limit": self.limit, "bounded": 1,
            "viewbox": box, "countrycodes": "cz", "accept-language": "cs",
            "addressdetails": 1, "extratags": 1, "namedetails": 1})
        req = urllib.request.Request(self.base + "/search?" + params,
                                     headers={"User-Agent": "hillview-enrich/0.1"})
        out = []
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                for d in json.loads(r.read()):
                    out.append({"display": d.get("display_name", ""),
                                "lat": float(d["lat"]), "lon": float(d["lon"]),
                                "cls": d.get("category") or d.get("class", ""),
                                "type": d.get("type", ""),
                                "importance": round(float(d.get("importance", 0) or 0), 3),
                                "rank": d.get("place_rank", ""),
                                "addrtype": d.get("addresstype", "")})
        except Exception as e:
            out = {"error": str(e)[:80]}
        self.cache[key] = out
        self.calls += 1
        if self.calls % 20 == 0:
            self.save()
        time.sleep(self.delay)
        return out


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
            out[r["id"]] = {"lon": ll[0], "lat": ll[1], "ar": max(w, h) / min(w, h) if w and h else 0,
                            "bearing": float(comp) if comp else None,
                            "desc": (r.get("description") or "").strip()}
    return out


def load_annotations(path):
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("is_current") not in ("t", "true", "True", "1"):
                continue
            out.append({"id": row["id"], "photo_id": row["photo_id"],
                        "body": (row.get("body") or "").strip()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--nominatim", default="https://nominatim.ueueeu.eu")
    ap.add_argument("--span", type=float, default=0.3)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--delay", type=float, default=0.15)
    ap.add_argument("--min-ar", type=float, default=2.0)
    args = ap.parse_args()

    photos = load_photos(find_csv(args.data, "photos"))
    anns = load_annotations(find_csv(args.data, "photo_annotations"))
    by_photo = {}
    for a in anns:
        by_photo.setdefault(a["photo_id"], []).append(a)
    panos = sorted([pid for pid in by_photo if pid in photos and photos[pid]["ar"] >= args.min_ar],
                   key=lambda pid: -len(by_photo[pid]))

    dbg = Debugger(args.nominatim, args.span, args.delay, args.limit,
                   os.path.join(HERE, ".geocode_debug_cache.json"))
    stat = {"queries": 0, "noresult": 0, "rerank_helps": 0, "no_good": 0, "top_ok": 0}
    sections = []
    toc = []
    for pid in panos:
        p = photos[pid]
        rows_html = ""
        nq = 0
        for a in by_photo[pid]:
            name, uncertain = clean_label(a["body"])
            if not name:
                continue                       # body-coords or no-name: not a query
            nq += 1
            stat["queries"] += 1
            cands = dbg.query(name, p["lat"], p["lon"])
            err = isinstance(cands, dict)
            # enrich candidates
            rich = []
            if not err:
                for i, c in enumerate(cands):
                    km = haversine_km(p["lon"], p["lat"], c["lon"], c["lat"])
                    az = bearing_deg(p["lon"], p["lat"], c["lon"], c["lat"])
                    db = ang_norm(az - p["bearing"]) if p["bearing"] is not None else None
                    rich.append({**c, "km": km, "db": db, "iv": in_view(km, db)})
            # diagnosis
            if err:
                diag, dcol = f"error: {cands['error']}", "#c00"
                stat["noresult"] += 1
            elif not rich:
                diag, dcol = "NO RESULT — bounded viewbox returned nothing", "#c00"
                stat["noresult"] += 1
            else:
                top_iv = rich[0]["iv"]
                better = next((i for i, c in enumerate(rich) if c["iv"]), None)
                if top_iv:
                    diag, dcol = "top-1 in-view ✓", "#070"
                    stat["top_ok"] += 1
                elif better is not None:
                    diag, dcol = f"RERANK: top-1 off-view, candidate #{better} is in-view", "#b60"
                    stat["rerank_helps"] += 1
                else:
                    diag, dcol = "no in-view candidate (ambiguous / out of area)", "#c00"
                    stat["no_good"] += 1
            # candidate table
            ctab = ""
            if not err:
                for i, c in enumerate(rich):
                    mark = "★" if i == 0 else ""
                    ivc = "#070" if c["iv"] else "#999"
                    ctab += (f'<tr style="color:{ivc}"><td>{mark}{i}</td>'
                             f'<td>{html.escape(c["display"][:54])}</td>'
                             f'<td>{c["cls"]}/{c["type"]}</td><td>{c["importance"]}</td>'
                             f'<td>{c["rank"]}</td><td>{c["km"]:.1f}</td>'
                             f'<td>{c["db"]:+.0f}</td></tr>' if c["db"] is not None else
                             f'<tr style="color:{ivc}"><td>{mark}{i}</td>'
                             f'<td>{html.escape(c["display"][:54])}</td>'
                             f'<td>{c["cls"]}/{c["type"]}</td><td>{c["importance"]}</td>'
                             f'<td>{c["rank"]}</td><td>{c["km"]:.1f}</td><td>?</td></tr>')
            rows_html += (
                f'<div class=q id="ann_{a["id"]}">'
                f'<div><b>{html.escape(a["body"][:70])}</b>{" ⟨?⟩" if uncertain else ""} '
                f'&nbsp;→ search: <code>{html.escape(name)}</code></div>'
                f'<div style="color:{dcol}">{diag}</div>'
                + (f'<table><tr><th>#</th><th>nominatim result</th><th>class/type</th>'
                   f'<th>imp</th><th>rank</th><th>km</th><th>Δbrg</th></tr>{ctab}</table>'
                   if ctab else "")
                + '</div>')
        toc.append(f'<a href="#pano_{pid[:8]}">{pid[:8]}</a> ({nq})')
        sections.append(f'<h3 id="pano_{pid[:8]}">{pid[:8]} — {html.escape(p["desc"][:55])} '
                        f'<small>(bearing {p["bearing"]}, {nq} queries)</small></h3>{rows_html}')
    dbg.save()

    doc = f"""<!doctype html><meta charset=utf-8><title>geocode debug</title>
<style>body{{font:13px system-ui;margin:24px;max-width:1000px}}
.q{{border-top:1px solid #eee;padding:7px 0;margin:0}}
code{{background:#f3f3f3;padding:1px 4px}}
table{{margin:4px 0 4px 16px;border-collapse:collapse}}
td,th{{padding:1px 7px;font-size:12px;text-align:left}}
h3{{margin-top:24px}} a{{margin-right:8px}}</style>
<h2>Geocoding debug — candidates &amp; diagnosis (for lookup tuning)</h2>
<p>{stat['queries']} queries · top-1 in-view <b style=color:#070>{stat['top_ok']}</b> ·
<b style=color:#b60>rerank-would-help {stat['rerank_helps']}</b> ·
no-good-candidate {stat['no_good']} · no-result {stat['noresult']}</p>
<p style=color:#888>Each query: full body → searched string → Nominatim candidates (★=current
pick). Green row = in-view (|Δbrg|≤60°, 0.2–35 km). "RERANK" = a lower candidate fits the
pano's view better than the top pick — i.e. re-ranking by bearing/distance would fix it.
viewbox span {args.span}°, bounded, cc=cz, limit {args.limit}.</p>
<p><b>panos:</b> {' '.join(toc)}</p>
{''.join(sections)}"""
    out = os.path.join(HERE, "geocode_debug.html")
    open(out, "w").write(doc)
    print(f"\n{stat}")
    print(f"HTML: {out}")


if __name__ == "__main__":
    main()
