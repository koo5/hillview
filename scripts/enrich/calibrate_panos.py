#!/usr/bin/env python3
"""
Per-pano calibration + outlier detection from the anchor set (no network).

For each pano, the clean anchors give (rectangle-x, geocoded-azimuth) pairs. A
robust Theil-Sen fit of azimuth-vs-x yields:
  * bias   = fitted bearing at pano centre (x=0.5) minus the stored compass_angle
             -> the magnetometer error (the thing we've been chasing)
  * FOV    = slope over x in [0,1]  (effective angular width of the delivered crop)
  * residuals -> anchors that don't fit the trend its neighbours trace are flagged
             as probable bad geocodes (the CONSENSUS flags the odd one out -
             NOT circular, and catches subtle errors the bearing/distance gate can't)

Then a cross-pano pass: names appearing on >=2 panos, with each occurrence's
inlier/outlier status (a name that's an inlier on one pano but an outlier on
another is inconsistent -> review).

Caveat: the fit is linear (equirectangular). Rectilinear panos (e.g. 333e8851 f0)
will show mildly curved residuals; bias at centre is still meaningful.

Usage: python calibrate_panos.py --data ~/hggg
"""
import argparse
import csv
import glob
import json
import math
import os
import struct
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
HERE = os.path.dirname(os.path.abspath(__file__))


def find_csv(d, p):
    h = sorted(glob.glob(os.path.join(d, p + "*.csv")))
    if not h:
        raise FileNotFoundError(p)
    return h[-1]


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
    if g.lower().startswith("0101000020"):
        try:
            b = bytes.fromhex(g)
            return struct.unpack_from("<d", b, 9)[0], struct.unpack_from("<d", b, 17)[0]
        except Exception:
            return None
    return None


def bearing_deg(lo1, la1, lo2, la2):
    p1, p2 = math.radians(la1), math.radians(la2)
    dl = math.radians(lo2 - lo1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def ang_norm(d):
    return (d + 180.0) % 360.0 - 180.0


def median(v):
    v = sorted(v)
    n = len(v)
    return None if n == 0 else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def theil_sen(xs, ys):
    sl = [(ys[j] - ys[i]) / (xs[j] - xs[i])
          for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] != xs[i]]
    if not sl:
        return None
    b = median(sl)
    a = median([y - b * x for x, y in zip(xs, ys)])
    return a, b


def load_cameras(path):
    out = {}
    for r in csv.DictReader(open(path)):
        if r.get("deleted") in ("t", "true", "True", "1"):
            continue
        ll = parse_point(r.get("geometry"))
        if not ll:
            continue
        comp = r.get("compass_angle")
        out[r["id"]] = {"lon": ll[0], "lat": ll[1],
                        "bearing": float(comp) if comp else None,
                        "desc": (r.get("description") or "").strip()}
    return out


def load_cx(path):
    cx = {}
    for row in csv.DictReader(open(path)):
        if row.get("is_current") not in ("t", "true", "True", "1"):
            continue
        try:
            g = (json.loads(row["target"]).get("selector") or {}).get("geometry") or {}
            cx[row["id"]] = float(g["x"]) + float(g.get("w", 0)) / 2.0
        except Exception:
            pass
    return cx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--anchors", default=os.path.join(HERE, "annotation_anchors.csv"))
    args = ap.parse_args()

    cams = load_cameras(find_csv(args.data, "photos"))
    cx = load_cx(find_csv(args.data, "photo_annotations"))
    anchors = [r for r in csv.DictReader(open(args.anchors)) if r["lat"] and not r["flag"]]

    by_pano = defaultdict(list)
    for r in anchors:
        if r["ann_id"] in cx and r["photo_id"] in cams:
            c = cams[r["photo_id"]]
            if c["bearing"] is None:
                continue
            az = bearing_deg(c["lon"], c["lat"], float(r["lon"]), float(r["lat"]))
            by_pano[r["photo_id"]].append({
                "x": cx[r["ann_id"]], "delta": ang_norm(az - c["bearing"]),
                "name": r["body"].split("|")[0].strip(), "ann": r["ann_id"]})

    results = {}
    inlier_status = {}     # ann_id -> bool
    for pid, pts in by_pano.items():
        if len(pts) < 4:
            results[pid] = {"n": len(pts), "skip": "too few"}
            continue
        xs = [p["x"] for p in pts]
        ys = [p["delta"] for p in pts]
        fit = theil_sen(xs, ys)
        if not fit:
            results[pid] = {"n": len(pts), "skip": "degenerate"}
            continue
        a, b = fit
        res = [y - (a + b * x) for x, y in zip(xs, ys)]
        mad = median([abs(r - median(res)) for r in res]) or 0.0
        thr = max(2.5 * mad * 1.4826, 6.0)
        outl = []
        for p, r in zip(pts, res):
            ok = abs(r) <= thr
            inlier_status[p["ann"]] = ok
            if not ok:
                outl.append((p["name"], r))
        inl = [r for r in res if abs(r) <= thr]
        rms = math.sqrt(sum(r * r for r in inl) / len(inl)) if inl else 0
        results[pid] = {"n": len(pts), "bias": a + b * 0.5, "fov": abs(b),
                        "rms": rms, "outl": outl, "nout": len(outl),
                        "bearing": cams[pid]["bearing"], "desc": cams[pid]["desc"]}

    # report
    fitted = {k: v for k, v in results.items() if "bias" in v}
    print(f"panos fitted: {len(fitted)} / {len(results)}")
    print(f"\n{'pano':9}{'n':>4}{'FOV':>7}{'bias':>8}{'RMS':>6}{'out':>5}  desc")
    for pid, v in sorted(fitted.items(), key=lambda kv: -kv[1]["n"]):
        print(f"{pid[:8]:9}{v['n']:>4}{v['fov']:>7.0f}{v['bias']:>+8.1f}{v['rms']:>6.1f}"
              f"{v['nout']:>5}  {v['desc'][:34]}")
    biases = [v["bias"] for v in fitted.values()]
    if biases:
        mb = median(biases)
        spread = median([abs(b - mb) for b in biases]) * 1.4826
        print(f"\nBIAS across panos: median {mb:+.1f}deg, robust spread ~{spread:.1f}deg")
        print("  => " + ("SYSTEMATIC (a global offset would help)" if spread < 8 else
                          "mostly PER-PANO (varies shoot to shoot)"))

    # cross-pano duplicate-name consistency
    byname = defaultdict(list)
    for pid, pts in by_pano.items():
        for p in pts:
            byname[p["name"].lower()].append((pid, p["ann"], p["name"]))
    dups = {n: v for n, v in byname.items()
            if len({pid for pid, _, _ in v}) >= 2}
    incons = []
    for n, occ in dups.items():
        sts = [(pid, inlier_status.get(ann)) for pid, ann, _ in occ]
        if any(s is False for _, s in sts) and any(s is True for _, s in sts):
            incons.append((occ[0][2], sts))
    print(f"\nduplicate-name POIs (on >=2 panos): {len(dups)};  "
          f"inconsistent (inlier on one, outlier on another): {len(incons)}")
    for name, sts in incons[:12]:
        print(f"  {name[:30]:30} " + " ".join(f"{pid[:6]}:{'in' if s else 'OUT' if s is False else '?'}"
                                              for pid, s in sts))

    # HTML
    rows = ""
    for pid, v in sorted(fitted.items(), key=lambda kv: -kv[1]["n"]):
        ol = ", ".join(f"{html_esc(n)}({r:+.0f})" for n, r in v["outl"][:8])
        rows += (f"<tr><td>{pid[:8]}</td><td>{html_esc(v['desc'][:38])}</td><td>{v['n']}</td>"
                 f"<td>{v['fov']:.0f}</td><td><b>{v['bias']:+.1f}</b></td><td>{v['rms']:.1f}</td>"
                 f"<td>{v['nout']}</td><td style=color:#c00>{ol}</td></tr>")
    drows = ""
    for name, sts in incons:
        drows += (f"<tr><td>{html_esc(name[:34])}</td><td>" +
                  " ".join(f"{pid[:6]}:<b style='color:{'#070' if s else '#c00'}'>"
                           f"{'in' if s else 'OUT'}</b>" for pid, s in sts) + "</td></tr>")
    doc = f"""<!doctype html><meta charset=utf-8><title>pano calibration</title>
<style>body{{font:13px system-ui;margin:24px;max-width:980px}}td,th{{padding:3px 8px;
border-bottom:1px solid #eee;font-size:12px;text-align:left}}</style>
<h2>Per-pano calibration &amp; geocode-outlier detection</h2>
<p>Robust (Theil-Sen) fit of geocoded azimuth vs rectangle-x per pano.
<b>bias</b> = fitted centre bearing − stored compass (the magnetometer error);
<b>FOV</b> = effective angular width; <b>out</b> = anchors flagged as geocode outliers
(residual beyond robust threshold).</p>
<p>BIAS across panos: median <b>{median(biases):+.1f}°</b>, spread ~{median([abs(b-median(biases)) for b in biases])*1.4826:.1f}° —
{"systematic" if median([abs(b-median(biases)) for b in biases])*1.4826 < 8 else "per-pano"}.</p>
<table><tr><th>pano</th><th>desc</th><th>n</th><th>FOV°</th><th>bias°</th><th>RMS°</th>
<th>outliers</th><th>flagged labels (residual)</th></tr>{rows}</table>
<h3>Cross-pano inconsistencies ({len(incons)})</h3>
<p style=color:#888>same name, inlier on one pano but outlier on another → review.</p>
<table><tr><th>name</th><th>per-pano status</th></tr>{drows}</table>"""
    open(os.path.join(HERE, "pano_calibration.html"), "w").write(doc)
    print("\nHTML: scripts/enrich/pano_calibration.html")


def html_esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    main()
