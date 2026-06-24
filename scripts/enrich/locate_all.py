#!/usr/bin/env python3
"""
locate_all — feature-match EVERY pano annotation to corpus close-ups (Track B), to
locate the unlabeled ones AND cross-check the geocoded ones. No label required.

Per annotation, gate candidate close-ups two ways then DISK+LightGlue match:
  * geocoded anchor present -> search within --radius of its coords, bearing-gated to
    the pano->anchor direction (proximity-transfer; also cross-checks the geocode)
  * no geocode ('?' / no-result) -> cast the CALIBRATED RAY (per-pano Theil-Sen fit of
    azimuth-vs-x) and gate photos lying along it + looking back along it
Matched close-ups (inliers >= --min-inliers) vote: inlier-weighted mean GPS = the POI.

Feature cache: DISK features per corpus image extracted once, reused across annotations.

Run with the venv:
  scripts/enrich/.venv/bin/python scripts/enrich/locate_all.py --pano 6ed01a83   # one
  scripts/enrich/.venv/bin/python scripts/enrich/locate_all.py --all             # all 19
"""
import argparse
import csv
import glob
import io
import json
import math
import os
import sys
import urllib.request

csv.field_size_limit(10 ** 9)
HERE = os.path.dirname(os.path.abspath(__file__))


def find_csv(d, p):
    return sorted(glob.glob(os.path.join(d, p + "*.csv")))[-1]


def wkt(g):
    if g and g.upper().startswith("POINT"):
        lo, la = g[g.index("(") + 1:g.index(")")].split()
        return float(lo), float(la)
    return None


def hav_m(a, b):
    R = 6371000
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = math.radians(b[1] - a[1]), math.radians(b[0] - a[0])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def brng(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dl = math.radians(b[0] - a[0])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def angn(d):
    return (d + 180) % 360 - 180


def ray_t(P, A, C, Bp):
    """Signed distance along the ray from P at azimuth A to its intersection with the
    ray from C at azimuth Bp (local planar approx). None if near-parallel."""
    latr = math.radians(P[1])
    cx = (C[0] - P[0]) * 111320 * math.cos(latr)
    cy = (C[1] - P[1]) * 110540
    a, b = math.radians(A), math.radians(Bp)
    ux, uy = math.sin(a), math.cos(a)
    vx, vy = math.sin(b), math.cos(b)
    den = -ux * vy + vx * uy
    if abs(den) < 1e-9:
        return None
    return (-cx * vy + vx * cy) / den


def median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else None


def theil_sen(xs, ys):
    sl = [(ys[j] - ys[i]) / (xs[j] - xs[i])
          for i in range(len(xs)) for j in range(i + 1, len(xs)) if xs[j] != xs[i]]
    if not sl:
        return None
    b = median(sl)
    return median([y - b * x for x, y in zip(xs, ys)]), b


def fetch_pil(url, _c={}):
    if url in _c:
        return _c[url]
    from PIL import Image
    req = urllib.request.Request(url, headers={"User-Agent": "hillview-enrich/0.2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    if len(_c) < 64:
        _c[url] = im
    return im


def to_tensor(pil, max_side, torch):
    import numpy as np
    w, h = pil.size
    s = min(1.0, max_side / max(w, h))
    if s < 1.0:
        pil = pil.resize((max(1, int(w * s)), max(1, int(h * s))))
    return torch.from_numpy((np.asarray(pil).astype("float32") / 255.0)).permute(2, 0, 1)[None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--anchors", default=os.path.join(HERE, "annotation_anchors.csv"))
    ap.add_argument("--pano", default=None, help="single pano id prefix")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--radius", type=float, default=400)
    ap.add_argument("--ray-wedge", type=float, default=10, help="deg around the calibrated ray")
    ap.add_argument("--ray-max-km", type=float, default=25)
    ap.add_argument("--bearing-tol", type=float, default=70)
    ap.add_argument("--topk", type=int, default=6)
    ap.add_argument("--min-inliers", type=int, default=8)
    ap.add_argument("--maxkp", type=int, default=2048)
    ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--margin-frac", type=float, default=0.10,
                    help="expand each annotation rect by this fraction of its OWN size, per side")
    ap.add_argument("--limit", type=int, default=0, help="cap annotations (debug)")
    args = ap.parse_args()

    import numpy as np
    import torch
    import cv2
    import kornia.feature as KF

    # data
    photos = {}
    for r in csv.DictReader(open(find_csv(args.data, "photos"))):
        ll = wkt(r.get("geometry"))
        if not ll:
            continue
        try:
            full = (json.loads(r["sizes"]).get("full") or {}).get("url")
        except Exception:
            full = None
        cb = r.get("compass_angle")
        anon = []
        try:
            for o in (json.loads(r.get("detected_objects") or "{}").get("objects") or []):
                bb = o.get("bbox") or {}
                if all(k in bb for k in ("x1", "y1", "x2", "y2")):
                    anon.append((bb["x1"], bb["y1"], bb["x2"], bb["y2"]))
        except Exception:
            pass
        photos[r["id"]] = {"ll": ll, "full": full, "brg": float(cb) if cb else None, "anon": anon}
    rects = {}
    for row in csv.DictReader(open(find_csv(args.data, "photo_annotations"))):
        if row.get("is_current") in ("t", "true", "True", "1"):
            try:
                g = (json.loads(row["target"]).get("selector") or {}).get("geometry") or {}
                x_, y_ = float(g["x"]), float(g["y"])
                w_, h_ = float(g.get("w", 0)), float(g.get("h", 0))
                if 0 <= x_ <= 1 and 0 <= y_ <= 1 and 0 < w_ <= 1 and 0 < h_ <= 1:
                    rects[row["id"]] = (x_, y_, w_, h_)   # skip pixel-valued / malformed rects
            except Exception:
                pass
    anns = list(csv.DictReader(open(args.anchors)))
    by_pano = {}
    for a in anns:
        by_pano.setdefault(a["photo_id"], []).append(a)

    panos = [args.pano and next(p for p in by_pano if p.startswith(args.pano))] if args.pano \
        else sorted(by_pano, key=lambda p: -len(by_pano[p]))
    panos = [p for p in panos if p in photos and photos[p]["full"]]

    dev = "cpu"
    disk = KF.DISK.from_pretrained("depth").to(dev).eval()
    lg = KF.LightGlue("disk").to(dev).eval()
    fcache = {}

    def extract(pil, key=None, boxes=None):
        if key is not None and key in fcache:
            return fcache[key]
        t = to_tensor(pil, args.max_side, torch).to(dev)
        with torch.inference_mode():
            f = disk(t, args.maxkp, pad_if_not_divisible=True)[0]
        kpts, desc = f.keypoints, f.descriptors
        if boxes:                                  # drop keypoints inside anonymization boxes
            s = min(1.0, args.max_side / max(pil.size))
            kp = kpts.cpu().numpy()
            keep = np.ones(len(kp), bool)
            for (x1, y1, x2, y2) in boxes:
                keep &= ~((kp[:, 0] >= x1 * s) & (kp[:, 0] <= x2 * s)
                          & (kp[:, 1] >= y1 * s) & (kp[:, 1] <= y2 * s))
            kt = torch.from_numpy(keep)
            kpts, desc = kpts[kt], desc[kt]
        out = (kpts, desc, torch.tensor([t.shape[-1], t.shape[-2]], dtype=torch.float32))
        if key is not None and len(fcache) < 1500:
            fcache[key] = out
        return out

    def match(f0, f1):
        inp = {"image0": {"keypoints": f0[0][None], "descriptors": f0[1][None], "image_size": f0[2][None]},
               "image1": {"keypoints": f1[0][None], "descriptors": f1[1][None], "image_size": f1[2][None]}}
        with torch.inference_mode():
            mm = lg(inp)["matches"][0].cpu().numpy()
        if len(mm) < 8:
            return 0
        p0 = f0[0].cpu().numpy()[mm[:, 0]]
        p1 = f1[0].cpu().numpy()[mm[:, 1]]
        _, mask = cv2.findFundamentalMat(p0, p1, cv2.FM_RANSAC, 3.0, 0.99)
        return int(mask.sum()) if mask is not None else 0

    out_csv = os.path.join(HERE, "locate_all.csv")
    cols = ["pano", "ann_id", "body", "mode", "n_cand", "n_match", "best_inl",
            "match_lat", "match_lon", "ray_dist_m", "spread_m", "nearest_photo_m", "geocode_dist_m"]
    fout = open(out_csv, "w", newline="")
    w = csv.DictWriter(fout, fieldnames=cols)
    w.writeheader()

    done = 0
    tally = {"total": 0, "matched": 0, "geo_xcheck_ok": 0, "geo_xcheck_n": 0, "new_located": 0}
    for pid in panos:
        cam = photos[pid]
        pano_ll = cam["ll"]
        loc_anchors = [(rects[a["ann_id"]][0] + rects[a["ann_id"]][2] / 2,
                        ang_to(cam, a))
                       for a in by_pano[pid]
                       if a["lat"] and not a["flag"] and a["ann_id"] in rects]
        fit = theil_sen([x for x, _ in loc_anchors], [y for _, y in loc_anchors]) \
            if len(loc_anchors) >= 4 else None
        pano_pil = None
        for a in by_pano[pid]:
            if args.limit and done >= args.limit:
                break
            aid = a["ann_id"]
            if aid not in rects or a["source"] in ("oops",):
                continue
            tally["total"] += 1
            done += 1
            x, y, ww, hh = rects[aid]
            cx = x + ww / 2
            # pano ray azimuth (calibrated fit; fallback to geocode bearing in geo mode)
            A = ((cam["brg"] + fit[0] + fit[1] * cx) % 360) if (fit and cam["brg"] is not None) else None
            if a["lat"]:
                aco = (float(a["lon"]), float(a["lat"]))
                B = brng(pano_ll, aco)
                if A is None:
                    A = B
                pool = [(abs(angn(p["brg"] - B)), pid2, p) for pid2, p in photos.items()
                        if pid2 != pid and p["full"] and hav_m(aco, p["ll"]) < args.radius
                        and p["brg"] is not None and abs(angn(p["brg"] - B)) <= args.bearing_tol]
                pool.sort(key=lambda t: t[0])
                mode = "geo"
            elif A is not None:
                pool = []
                for pid2, p in photos.items():
                    if pid2 == pid or not p["full"] or p["brg"] is None:
                        continue
                    d = hav_m(pano_ll, p["ll"])
                    if not (50 < d < args.ray_max_km * 1000):
                        continue
                    if abs(angn(brng(pano_ll, p["ll"]) - A)) > args.ray_wedge:
                        continue
                    if abs(angn(p["brg"] - A)) > args.bearing_tol:
                        continue
                    pool.append((abs(angn(p["brg"] - A)), pid2, p))
                pool.sort(key=lambda t: t[0])
                mode = "ray"
            else:
                continue
            cands = pool[:args.topk]
            if not cands:
                w.writerow({"pano": pid[:8], "ann_id": aid, "body": a["body"][:40],
                            "mode": mode, "n_cand": 0, "n_match": 0, "best_inl": 0,
                            "match_lat": "", "match_lon": "", "spread_m": "", "geocode_dist_m": ""})
                continue
            if pano_pil is None:
                pano_pil = fetch_pil(cam["full"])
            W, H = pano_pil.size
            mgx = max(args.margin_frac * ww, 0.005)   # slack: ~10% of the rect's OWN size per side
            mgy = max(args.margin_frac * hh, 0.005)    # (small image-relative floor for hairline rects)
            x0 = min(W, max(0, int((x - mgx) * W)))
            y0 = min(H, max(0, int((y - mgy) * H)))
            x1 = min(W, max(0, int((x + ww + mgx) * W)))
            y1 = min(H, max(0, int((y + hh + mgy) * H)))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            try:
                fq = extract(pano_pil.crop((x0, y0, x1, y1)))
            except Exception:
                continue
            matched = []
            for _, pid2, p in cands:
                try:
                    fc = extract(fetch_pil(p["full"]), key=p["full"], boxes=p.get("anon"))
                    inl = match(fq, fc)
                except Exception:
                    inl = 0
                if inl >= args.min_inliers and p["brg"] is not None:
                    matched.append((inl, p["ll"], p["brg"]))
            best = max((m[0] for m in matched), default=0)
            row = {"pano": pid[:8], "ann_id": aid, "body": a["body"][:40], "mode": mode,
                   "n_cand": len(cands), "n_match": len(matched), "best_inl": best,
                   "match_lat": "", "match_lon": "", "ray_dist_m": "", "spread_m": "",
                   "nearest_photo_m": "", "geocode_dist_m": ""}
            # triangulate: POI = where each matched photo's bearing-ray crosses the pano ray A
            ts = [t for inl, ll, br in matched
                  if (t := ray_t(pano_ll, A, ll, br)) is not None and 30 < t < args.ray_max_km * 1000]
            if ts:
                tally["matched"] += 1
                tmed = median(ts)
                latr = math.radians(pano_ll[1])
                poi = (pano_ll[0] + (tmed * math.sin(math.radians(A))) / (111320 * math.cos(latr)),
                       pano_ll[1] + (tmed * math.cos(math.radians(A))) / 110540)
                nearest = min(hav_m(ll, poi) for _, ll, _ in matched)
                row.update(match_lat=f"{poi[1]:.5f}", match_lon=f"{poi[0]:.5f}",
                           ray_dist_m=f"{tmed:.0f}", spread_m=f"{max(ts) - min(ts):.0f}",
                           nearest_photo_m=f"{nearest:.0f}")
                if a["lat"]:
                    gd = hav_m((float(a["lon"]), float(a["lat"])), poi)
                    row["geocode_dist_m"] = f"{gd:.0f}"
                    tally["geo_xcheck_n"] += 1
                    if gd < 150:
                        tally["geo_xcheck_ok"] += 1
                else:
                    tally["new_located"] += 1
            w.writerow(row)
            fout.flush()
        nm = sum(1 for a in by_pano[pid])
        print(f"  {pid[:8]} done ({len([1 for a in by_pano[pid]])} annos)  "
              f"running matched={tally['matched']}/{tally['total']}", flush=True)
        if args.limit and done >= args.limit:
            break
    fout.close()
    print(f"\n{tally}")
    print(f"CSV: {out_csv}")


def ang_to(cam, a):
    return angn(brng(cam["ll"], (float(a["lon"]), float(a["lat"]))) - cam["brg"]) \
        if cam["brg"] is not None else 0.0


if __name__ == "__main__":
    main()
