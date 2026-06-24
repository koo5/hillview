#!/usr/bin/env python3
"""
r2_match — feature-match a pano region against nearby corpus photos (proximity-transfer).

Pipeline (recipe R2 / Track B, the independent label-free check):
  * take a located anchor on a pano (from annotation_anchors.csv) + its rectangle
  * crop the pano's `full` image to that rectangle (the distant POI)
  * candidates = corpus photos within --radius of the anchor's geocoded coords
    (these should be CLOSE-UP shots of the same POI)
  * DISK + LightGlue match the crop vs each candidate, RANSAC-verify
  * the best match's GPS ~= the POI location (proximity-transfer); compare to the
    geocoded anchor -> independent cross-check of the geocode

Run with the venv:
  scripts/enrich/.venv/bin/python scripts/enrich/r2_match.py \
     --pano 6ed01a83 --anchor "Vitkov" --radius 300

Outputs r2_match_<pano>.html with the crop, matched candidates, drawn inliers.
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
    h = sorted(glob.glob(os.path.join(d, p + "*.csv")))
    if not h:
        raise FileNotFoundError(p)
    return h[-1]


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


def fetch_pil(url, _cache={}):
    if url in _cache:
        return _cache[url]
    from PIL import Image
    req = urllib.request.Request(url, headers={"User-Agent": "hillview-enrich/0.2"})
    with urllib.request.urlopen(req, timeout=60) as r:
        im = Image.open(io.BytesIO(r.read())).convert("RGB")
    _cache[url] = im
    return im


def to_tensor(pil, max_side, torch):
    import numpy as np
    w, h = pil.size
    s = min(1.0, max_side / max(w, h))
    if s < 1.0:
        pil = pil.resize((max(1, int(w * s)), max(1, int(h * s))))
    arr = np.asarray(pil).astype("float32") / 255.0
    t = torch.from_numpy(arr).permute(2, 0, 1)[None]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    ap.add_argument("--anchors", default=os.path.join(HERE, "annotation_anchors.csv"))
    ap.add_argument("--pano", required=True, help="pano id prefix")
    ap.add_argument("--anchor", default="", help="substring of the anchor body to pick")
    ap.add_argument("--radius", type=float, default=300, help="candidate radius, m")
    ap.add_argument("--max-cands", type=int, default=8)
    ap.add_argument("--bearing-tol", type=float, default=70,
                    help="keep close-ups whose bearing is within this of the pano's look direction B")
    ap.add_argument("--margin", type=float, default=0.05, help="crop margin (norm)")
    ap.add_argument("--maxkp", type=int, default=2048)
    ap.add_argument("--max-side", type=int, default=1024)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import numpy as np
    import torch
    import cv2
    import kornia.feature as KF

    # pick anchor
    anchors = [r for r in csv.DictReader(open(args.anchors))
               if r["lat"] and r["photo_id"].startswith(args.pano)]
    if args.anchor:
        anchors = [r for r in anchors if args.anchor.lower() in r["body"].lower()]
    if not anchors:
        sys.exit("no matching located anchor on that pano")
    a = anchors[0]
    pano_id = a["photo_id"]
    aco = (float(a["lon"]), float(a["lat"]))
    print(f"anchor: {a['body'][:50]}  @ {a['lat']},{a['lon']}  (pano {pano_id[:8]})")

    # rect for this annotation
    rect = None
    for row in csv.DictReader(open(find_csv(args.data, "photo_annotations"))):
        if row["id"] == a["ann_id"]:
            g = (json.loads(row["target"]).get("selector") or {}).get("geometry") or {}
            rect = (float(g["x"]), float(g["y"]), float(g["w"]), float(g["h"]))
            break
    if not rect:
        sys.exit("rect not found")

    # photos: coords + full url
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
        photos[r["id"]] = {"ll": ll, "full": full, "of": r.get("original_filename", ""),
                           "brg": float(cb) if cb else None}
    pano_full = photos[pano_id]["full"]

    pano_ll = photos[pano_id]["ll"]
    B = brng(pano_ll, aco)              # the pano's look direction to the POI
    pool = []
    for pid, p in photos.items():
        if pid == pano_id or not p["full"]:
            continue
        d = hav_m(aco, p["ll"])
        if d >= args.radius:
            continue
        p["_db"] = abs(angn(p["brg"] - B)) if p["brg"] is not None else 999.0
        pool.append((d, pid, p))
    aligned = [x for x in pool if x[2]["_db"] <= args.bearing_tol]
    use = aligned if len(aligned) >= 3 else pool      # fall back if bearing prunes too hard
    cands = sorted(use, key=lambda x: (x[2]["_db"], x[0]))[:args.max_cands]
    print(f"pano->POI bearing B={B:.0f}deg; {len(pool)} within {args.radius:.0f}m, "
          f"{len(aligned)} bearing-aligned (+-{args.bearing_tol:.0f}deg); matching top {len(cands)}")

    # crop pano to rect (+margin)
    pano = fetch_pil(pano_full)
    W, H = pano.size
    x, y, w, h = rect
    m = args.margin
    box = (max(0, int((x - m) * W)), max(0, int((y - m) * H)),
           min(W, int((x + w + m) * W)), min(H, int((y + h + m) * H)))
    crop = pano.crop(box)
    print(f"pano {W}x{H}, crop {crop.size}")

    dev = "cpu"
    disk = KF.DISK.from_pretrained("depth").to(dev).eval()
    lg = KF.LightGlue("disk").to(dev).eval()

    def extract(pil):
        t = to_tensor(pil, args.max_side, torch).to(dev)
        with torch.inference_mode():
            f = disk(t, args.maxkp, pad_if_not_divisible=True)[0]
        wh = torch.tensor([t.shape[-1], t.shape[-2]], dtype=torch.float32, device=dev)
        return f.keypoints, f.descriptors, wh

    def match(f0, f1):
        inp = {"image0": {"keypoints": f0[0][None], "descriptors": f0[1][None], "image_size": f0[2][None]},
               "image1": {"keypoints": f1[0][None], "descriptors": f1[1][None], "image_size": f1[2][None]}}
        with torch.inference_mode():
            out = lg(inp)
        return out["matches"][0]   # K x 2 indices

    fq = extract(crop)
    print(f"crop keypoints: {fq[0].shape[0]}")
    results = []
    for dist, pid, p in cands:
        try:
            cpil = fetch_pil(p["full"])
            fc = extract(cpil)
            mm = match(fq, fc).cpu().numpy()
            inl = 0
            mask = None
            if len(mm) >= 8:
                p0 = fq[0].cpu().numpy()[mm[:, 0]]
                p1 = fc[0].cpu().numpy()[mm[:, 1]]
                F, mask = cv2.findFundamentalMat(p0, p1, cv2.FM_RANSAC, 3.0, 0.99)
                inl = int(mask.sum()) if mask is not None else 0
            gps_err = hav_m(aco, p["ll"])
            results.append({"pid": pid, "of": p["of"], "dist": dist, "nm": len(mm),
                            "inl": inl, "gps_err": gps_err, "pil": cpil,
                            "fq": fq, "fc": fc, "mm": mm, "mask": mask})
            print(f"  {pid[:8]} d={dist:5.0f}m dbrg={p['_db']:4.0f}  matches={len(mm):4}  inliers={inl:3}  {p['of'][:24]}")
        except Exception as e:
            print(f"  {pid[:8]} ERROR {e}")
    results.sort(key=lambda r: -r["inl"])

    # HTML with drawn inliers for the top few
    def viz(crop, cpil, fq, fc, mm, mask):
        a1 = np.asarray(crop.resize_tensor if False else _resz(crop, args.max_side))
        return None  # placeholder; drawing below uses cv2 montage

    import base64

    def b64(pil):
        b = io.BytesIO()
        pil.save(b, "JPEG", quality=80)
        return base64.b64encode(b.getvalue()).decode()

    def draw(crop, cpil, fq, fc, mm, mask):
        ca = cv2.cvtColor(np.asarray(_resz(crop, args.max_side)), cv2.COLOR_RGB2BGR)
        pa = cv2.cvtColor(np.asarray(_resz(cpil, args.max_side)), cv2.COLOR_RGB2BGR)
        hh = max(ca.shape[0], pa.shape[0])
        canvas = np.zeros((hh, ca.shape[1] + pa.shape[1], 3), "uint8")
        canvas[:ca.shape[0], :ca.shape[1]] = ca
        canvas[:pa.shape[0], ca.shape[1]:] = pa
        k0 = fq[0].cpu().numpy()
        k1 = fc[0].cpu().numpy()
        for j, (i0, i1) in enumerate(mm):
            if mask is not None and not mask[j]:
                continue
            x0, y0 = k0[i0]
            x1, y1 = k1[i1]
            cv2.line(canvas, (int(x0), int(y0)), (int(x1) + ca.shape[1], int(y1)),
                     (0, 255, 0), 1)
        from PIL import Image
        return Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))

    rows = ""
    for r in results[:4]:
        try:
            img = draw(crop, r["pil"], r["fq"], r["fc"], r["mm"], r["mask"])
            tag = f'<img src="data:image/jpeg;base64,{b64(img)}" style="max-width:900px">'
        except Exception as e:
            tag = f"(viz error {e})"
        verdict = ("MATCH ✓" if r["inl"] >= 15 else "weak" if r["inl"] >= 6 else "no")
        rows += (f'<div style=margin:14px-0><b>{r["pid"][:8]}</b> · {r["of"][:34]} · '
                 f'{r["dist"]:.0f} m from anchor · matches {r["nm"]} · '
                 f'<b>inliers {r["inl"]} ({verdict})</b></div>{tag}')
    out = args.out or os.path.join(HERE, f"r2_match_{pano_id[:8]}.html")
    open(out, "w").write(
        f"<!doctype html><meta charset=utf-8><style>body{{font:13px system-ui;margin:20px}}"
        f"img{{border:1px solid #ccc}}</style>"
        f"<h2>r2_match — {a['body'][:50]} (pano {pano_id[:8]})</h2>"
        f"<p>left = pano crop (distant POI); right = nearby corpus photo; green = RANSAC inliers. "
        f"A real match validates proximity-transfer: that photo's GPS ≈ the POI.</p>"
        f"<p>crop {crop.size} · {len(cands)} candidates within {args.radius:.0f} m</p>{rows}")
    print(f"\nHTML: {out}")
    if results and results[0]["inl"] >= 15:
        b = results[0]
        print(f"BEST MATCH {b['pid'][:8]} inliers={b['inl']} -> proximity-transfer location is "
              f"that photo's GPS ({b['dist']:.0f} m from the geocoded anchor)")


def _resz(pil, max_side):
    w, h = pil.size
    s = min(1.0, max_side / max(w, h))
    return pil.resize((max(1, int(w * s)), max(1, int(h * s)))) if s < 1 else pil


if __name__ == "__main__":
    main()
