#!/usr/bin/env python3
"""
R2 / M1-0 feasibility probe (see docs/vision-subsystem.md, recipe R2).

Question this answers, using only the live CSV export (no ML, no network):
  For the clean single-frame gold photos (the ~8688x5792 5DS shots that were
  annotated directly), does the corpus contain OTHER photos that plausibly see
  or sit near the POIs in each frame?  If not, feature-matching has nothing to
  match against and R2 is moot before we touch LightGlue.

For each target frame F (position P, biased bearing B, far-clip from the LLM
`farthest_object_distance`), we count corpus photos that are:
  * FAN candidates  — within +/- tol of B and at range [near_min, far_clip]
                      from F (i.e. roughly out where the POIs are: potential
                      proximity-transfer targets / co-visible-from-along-the-ray)
  * NEAR candidates — within near_radius of F in any direction (other shots of
                      the same scene from a similar viewpoint: the easiest matches)

Usage:
  python r2_select_and_gate.py --data ~/hggg [--tol 35] [--near-radius 150]
"""
import argparse
import csv
import json
import math
import os
import struct
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)


def parse_point(g):
    """Parse a geometry cell: 'POINT(lon lat)' or little-endian EWKB hex -> (lon, lat)."""
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
        if g.lower().startswith("0101000020"):  # EWKB point w/ SRID
            b = bytes.fromhex(g)
            return struct.unpack_from("<d", b, 9)[0], struct.unpack_from("<d", b, 17)[0]
    except Exception:
        pass
    return None


def haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def ang_diff(a, b):
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    return d


def load_annotations(path):
    """photo_id -> list of current annotation bodies."""
    bodies = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            if row.get("is_current") in ("t", "true", "True", "1"):
                b = (row.get("body") or "").strip()
                bodies[row["photo_id"]].append(b)
    return bodies


def load_photos(path):
    photos = []
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
                w = h = 0
            far = None
            features = []
            an = (r.get("analysis") or "").strip()
            if an:
                try:
                    a = json.loads(an)
                    far = a.get("farthest_object_distance")
                    fl = a.get("features")
                    features = fl if isinstance(fl, list) else []
                except Exception:
                    pass
            comp = r.get("compass_angle")
            photos.append({
                "id": r["id"], "lon": ll[0], "lat": ll[1],
                "w": w, "h": h, "ar": (max(w, h) / min(w, h)) if w and h else 0,
                "bearing": float(comp) if comp else None,
                "far": float(far) if isinstance(far, (int, float)) else None,
                "features": set(features),
            })
    return photos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"),
                    help="dir holding photos.csv and photo_annotations.csv")
    ap.add_argument("--tol", type=float, default=35.0,
                    help="bearing half-window deg (covers magnetometer bias + FOV)")
    ap.add_argument("--near-radius", type=float, default=150.0, help="meters")
    ap.add_argument("--near-min", type=float, default=80.0,
                    help="min range for fan candidates (skip same-spot)")
    ap.add_argument("--default-far", type=float, default=15000.0,
                    help="far-clip when LLM distance is missing, meters")
    args = ap.parse_args()

    import glob as _glob
    def find_csv(prefix):
        hits = sorted(_glob.glob(os.path.join(args.data, prefix + "*.csv")))
        if not hits:
            raise FileNotFoundError(f"no {prefix}*.csv in {args.data}")
        return hits[-1]  # tolerate photos.csv / photos_1.csv dump naming

    photos = load_photos(find_csv("photos"))
    bodies = load_annotations(find_csv("photo_annotations"))
    by_id = {p["id"]: p for p in photos}

    # clean single-frame gold targets: annotated, ~3:2 aspect, full-res
    targets = [by_id[pid] for pid in bodies
               if pid in by_id and 1.4 <= by_id[pid]["ar"] <= 1.6
               and min(by_id[pid]["w"], by_id[pid]["h"]) >= 4000]
    targets.sort(key=lambda p: -len(bodies[p["id"]]))

    print(f"corpus photos (geo, not deleted): {len(photos)}")
    print(f"clean single-frame gold targets (aspect~1.5, >=4000px): {len(targets)}\n")

    hdr = f"{'frame':8} {'WxH':>11} {'brng':>5} {'far_m':>7} {'POIs':>4} {'fan':>5} {'near':>5}"
    print(hdr)
    print("-" * len(hdr))

    ranked = []
    for t in targets:
        far = t["far"] or args.default_far
        fan = near = 0
        cand_ids = []
        for p in photos:
            if p["id"] == t["id"]:
                continue
            d = haversine_m(t["lon"], t["lat"], p["lon"], p["lat"])
            if d <= args.near_radius:
                near += 1
            if t["bearing"] is not None and args.near_min <= d <= far:
                if ang_diff(bearing_deg(t["lon"], t["lat"], p["lon"], p["lat"]),
                            t["bearing"]) <= args.tol:
                    fan += 1
                    if len(cand_ids) < 5:
                        cand_ids.append(p["id"][:8])
        ranked.append((t, fan, near, cand_ids))
        b = f"{t['bearing']:.0f}" if t["bearing"] is not None else "--"
        print(f"{t['id'][:8]:8} {f'{t[chr(119)]}x{t[chr(104)]}':>11} {b:>5} "
              f"{far:>7.0f} {len(bodies[t['id']]):>4} {fan:>5} {near:>5}")

    ranked.sort(key=lambda x: -(x[1] + x[2]))
    if ranked:
        t, fan, near, cand_ids = ranked[0]
        print(f"\nbest target for R2: {t['id'][:8]}  (fan={fan}, near={near})")
        print(f"  features: {','.join(sorted(t['features'])) or '-'}")
        print(f"  sample fan-candidate ids: {', '.join(cand_ids) or '(none)'}")
        print(f"  POIs ({len(bodies[t['id']])}):")
        for b in bodies[t["id"]]:
            print(f"    - {b[:80] or '?'}")

    viable = sum(1 for _, fan, near, _ in ranked if fan + near >= 5)
    print(f"\nVERDICT: {viable}/{len(ranked)} targets have >=5 candidate photos "
          f"(fan+near). {'R2 is worth running.' if viable else 'Corpus too sparse here.'}")


if __name__ == "__main__":
    main()
