#!/usr/bin/env python3
"""
viz_app — local web inspector for the localization pipeline.

Browse every pano annotation; click one to see the REAL inputs and each step's
output, computed live:
  inputs (pano crop + gated candidate photos) -> DISK keypoints -> LightGlue
  matches -> RANSAC inliers -> ray-triangulation map (pano ray + candidate rays
  -> POI, vs geocode).

Run:  scripts/enrich/.venv/bin/python scripts/enrich/viz_app.py
Then open http://127.0.0.1:8765
"""
import base64
import csv
import glob
import io
import json
import math
import os
import sys
import threading
import urllib.request

import numpy as np
import cv2
import torch
import kornia.feature as KF
from flask import Flask, Response, abort, request, send_from_directory
from PIL import Image

csv.field_size_limit(10 ** 9)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.expanduser("~/hggg")
MAXKP, MAXSIDE, TOPK, MIN_INL = 1536, 1024, 6, 8
QUERY_MAXSIDE = 2048   # run DISK on the pano query-crop at higher res (full-res source)
LOFTR_MAXSIDE = 1024   # LoFTR is heavier; cap input resolution
MAST3R_REPO = os.path.join(HERE, "mast3r_repo")
MAST3R_CKPT = os.path.join(MAST3R_REPO, "checkpoints", "mast3r.pth")
VIEW_SLACK = 2      # trust the LLM farthest_object_distance to within ~2x (tunable via ?slack=)
FAR_DEFAULT = 2000  # assumed view depth (m) for photos missing an LLM farthest_object_distance
VIEW_HALF = 60      # a photo sees within ±60° of its compass bearing
SAME_SIDE = 90      # candidate must view the POI from within ±90° of the pano ray (same face)
BEAR_TOL, RADIUS, RAY_WEDGE, RAY_MAXKM, MARGIN = 70, 400, 10, 25, 0.10


def find_csv(p):
    return sorted(glob.glob(os.path.join(DATA, p + "*.csv")))[-1]


def wkt(g):
    if g and g.upper().startswith("POINT"):
        lo, la = g[g.index("(") + 1:g.index(")")].split()
        return float(lo), float(la)
    return None


def brng(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dl = math.radians(b[0] - a[0])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def hav_m(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = math.radians(b[1] - a[1]), math.radians(b[0] - a[0])
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(x))


def angn(d):
    return (d + 180) % 360 - 180


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


def ray_t(P, A, C, Bp):
    latr = math.radians(P[1])
    cx = (C[0] - P[0]) * 111320 * math.cos(latr)
    cy = (C[1] - P[1]) * 110540
    a, b = math.radians(A), math.radians(Bp)
    ux, uy, vx, vy = math.sin(a), math.cos(a), math.sin(b), math.cos(b)
    den = -ux * vy + vx * uy
    return None if abs(den) < 1e-9 else (-cx * vy + vx * cy) / den


def jb64(rgb):
    b = io.BytesIO()
    Image.fromarray(rgb).save(b, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def resz(pil, max_side=MAXSIDE):
    w, h = pil.size
    s = min(1.0, max_side / max(w, h))
    return pil.resize((max(1, int(w * s)), max(1, int(h * s)))) if s < 1 else pil


def dzi_region(pyr, nx0, ny0, nx1, ny1, fetch):
    """Full-res crop of a normalized region from the DZI pyramid metadata
    (sizes.full.pyramid: tiles_url/tile_size/overlap/format/width/height).
    Fetches only the tiles covering the region."""
    base, fmt = pyr["tiles_url"].rstrip("/"), pyr.get("format", "webp")
    TS, OV = int(pyr["tile_size"]), int(pyr["overlap"])
    W, H = int(pyr["width"]), int(pyr["height"])
    level = math.ceil(math.log2(max(W, H)))
    px0, px1 = sorted((max(0, int(nx0 * W)), min(W, int(nx1 * W))))
    py0, py1 = sorted((max(0, int(ny0 * H)), min(H, int(ny1 * H))))
    if px1 - px0 < 2 or py1 - py0 < 2:
        raise ValueError("empty region")
    c0, c1, r0, r1 = px0 // TS, (px1 - 1) // TS, py0 // TS, (py1 - 1) // TS
    ox, oy = c0 * TS, r0 * TS
    canvas = Image.new("RGB", ((c1 - c0 + 1) * TS + OV + 1, (r1 - r0 + 1) * TS + OV + 1))
    for c in range(c0, c1 + 1):
        for r in range(r0, r1 + 1):
            try:
                tile = fetch(f"{base}/{level}/{c}_{r}.{fmt}")
            except Exception:
                continue
            canvas.paste(tile, (c * TS - (OV if c > 0 else 0) - ox,
                                r * TS - (OV if r > 0 else 0) - oy))
    return canvas.crop((px0 - ox, py0 - oy, px1 - ox, py1 - oy))


class Engine:
    def __init__(self):
        print("loading data...", flush=True)
        self.photos = {}
        for r in csv.DictReader(open(find_csv("photos"))):
            ll = wkt(r.get("geometry"))
            if not ll:
                continue
            full = pyr = t640 = None
            try:
                sz = json.loads(r["sizes"])
                fe = sz.get("full") or {}
                full, pyr = fe.get("url"), fe.get("pyramid")
                t640 = (sz.get("640") or {}).get("url")
            except Exception:
                pass
            cb = r.get("compass_angle")
            anon = []
            try:
                for o in (json.loads(r.get("detected_objects") or "{}").get("objects") or []):
                    bb = o.get("bbox") or {}
                    if all(k in bb for k in ("x1", "y1", "x2", "y2")):
                        anon.append((bb["x1"], bb["y1"], bb["x2"], bb["y2"]))
            except Exception:
                pass
            try:
                pw, ph = int(r["width"]), int(r["height"])
            except Exception:
                pw = ph = 0
            far = None
            try:
                fv = json.loads(r.get("analysis") or "{}").get("farthest_object_distance")
                far = float(fv) if fv is not None else None
            except Exception:
                pass
            self.photos[r["id"]] = {"ll": ll, "full": full, "brg": float(cb) if cb else None,
                                    "desc": (r.get("description") or "").strip(), "anon": anon,
                                    "w": pw, "h": ph, "pyr": pyr, "far": far, "t640": t640}
        self.rects = {}
        for row in csv.DictReader(open(find_csv("photo_annotations"))):
            if row.get("is_current") in ("t", "true", "True", "1"):
                try:
                    g = (json.loads(row["target"]).get("selector") or {}).get("geometry") or {}
                    x_, y_, w_, h_ = float(g["x"]), float(g["y"]), float(g.get("w", 0)), float(g.get("h", 0))
                    if 0 <= x_ <= 1 and 0 <= y_ <= 1 and 0 < w_ <= 1 and 0 < h_ <= 1:
                        self.rects[row["id"]] = (x_, y_, w_, h_)
                except Exception:
                    pass
        self.anns = {a["ann_id"]: a for a in csv.DictReader(open(os.path.join(HERE, "annotation_anchors.csv")))}
        self.by_pano = {}
        for a in self.anns.values():
            self.by_pano.setdefault(a["photo_id"], []).append(a)
        self.fits = {}
        for pid, lst in self.by_pano.items():
            cam = self.photos.get(pid)
            if not cam or cam["brg"] is None:
                continue
            pts = [(self.rects[a["ann_id"]][0] + self.rects[a["ann_id"]][2] / 2,
                    angn(brng(cam["ll"], (float(a["lon"]), float(a["lat"]))) - cam["brg"]))
                   for a in lst if a["lat"] and not a["flag"] and a["ann_id"] in self.rects]
            if len(pts) >= 4:
                self.fits[pid] = theil_sen([p[0] for p in pts], [p[1] for p in pts])
        print("loading models...", flush=True)
        self.disk = KF.DISK.from_pretrained("depth").eval()
        self.lg = KF.LightGlue("disk").eval()
        self.lock = threading.Lock()
        self.fcache, self.imcache, self.case_cache = {}, {}, {}
        self.loftr = None
        self._m3 = None
        self._m3_fns = None
        print(f"ready: {len(self.by_pano)} panos, {len(self.anns)} annotations", flush=True)

    def fetch(self, url):
        if url in self.imcache:
            return self.imcache[url]
        req = urllib.request.Request(url, headers={"User-Agent": "hillview-enrich/0.2"})
        im = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=60).read())).convert("RGB")
        if len(self.imcache) < 80:
            self.imcache[url] = im
        return im

    def extract(self, pil, key=None, boxes=None, max_side=MAXSIDE):
        if key and key in self.fcache:
            return self.fcache[key]
        r = resz(pil, max_side)
        arr = np.asarray(r)
        t = torch.from_numpy(arr.astype("float32") / 255.0).permute(2, 0, 1)[None]
        with torch.inference_mode():
            f = self.disk(t, MAXKP, pad_if_not_divisible=True)[0]
        kpts, desc = f.keypoints, f.descriptors
        if boxes:                                  # drop keypoints inside anonymization boxes
            sw, sh = r.size[0] / pil.size[0], r.size[1] / pil.size[1]
            kp = kpts.cpu().numpy()
            keep = np.ones(len(kp), bool)
            for (x1, y1, x2, y2) in boxes:
                keep &= ~((kp[:, 0] >= x1 * sw) & (kp[:, 0] <= x2 * sw)
                          & (kp[:, 1] >= y1 * sh) & (kp[:, 1] <= y2 * sh))
            kt = torch.from_numpy(keep)
            kpts, desc = kpts[kt], desc[kt]
        out = (arr, kpts, desc, torch.tensor([t.shape[-1], t.shape[-2]], dtype=torch.float32))
        if key and len(self.fcache) < 400:
            self.fcache[key] = out
        return out

    def match(self, f0, f1):
        inp = {"image0": {"keypoints": f0[1][None], "descriptors": f0[2][None], "image_size": f0[3][None]},
               "image1": {"keypoints": f1[1][None], "descriptors": f1[2][None], "image_size": f1[3][None]}}
        with torch.inference_mode():
            mm = self.lg(inp)["matches"][0].cpu().numpy()
        mask = None
        if len(mm) >= 8:
            p0 = f0[1].cpu().numpy()[mm[:, 0]]
            p1 = f1[1].cpu().numpy()[mm[:, 1]]
            _, mask = cv2.findFundamentalMat(p0, p1, cv2.FM_RANSAC, 3.0, 0.99)
            mask = None if mask is None else mask.ravel().astype(bool)
        return mm, mask

    def run(self, aid):
        with self.lock:
            if aid not in self.case_cache:
                self.case_cache[aid] = self._run(aid)
            return self.case_cache[aid]

    def _run(self, aid):
        a = self.anns[aid]
        pid = a["photo_id"]
        cam = self.photos[pid]
        if aid not in self.rects:
            return {"error": "no rectangle for this annotation"}
        x, y, ww, hh = self.rects[aid]
        cx = x + ww / 2
        fit = self.fits.get(pid)
        A = ((cam["brg"] + fit[0] + fit[1] * cx) % 360) if (fit and cam["brg"] is not None) else None
        if a["lat"]:
            aco = (float(a["lon"]), float(a["lat"]))
            B = brng(cam["ll"], aco)
            if A is None:
                A = B
            pool = [(abs(angn(p["brg"] - B)), pid2, p) for pid2, p in self.photos.items()
                    if pid2 != pid and p["full"] and p["brg"] is not None
                    and hav_m(aco, p["ll"]) < RADIUS and abs(angn(p["brg"] - B)) <= BEAR_TOL]
            mode = "geo (search around geocode)"
        elif A is not None:
            aco = None
            pool = []
            for pid2, p in self.photos.items():
                if pid2 == pid or not p["full"] or p["brg"] is None:
                    continue
                d = hav_m(cam["ll"], p["ll"])
                if 50 < d < RAY_MAXKM * 1000 and abs(angn(brng(cam["ll"], p["ll"]) - A)) <= RAY_WEDGE \
                        and abs(angn(p["brg"] - A)) <= BEAR_TOL:
                    pool.append((abs(angn(p["brg"] - A)), pid2, p))
            mode = "ray (cast calibrated ray, no label)"
        else:
            return {"error": "pano not calibrated and no geocode"}
        pool.sort(key=lambda t: t[0])
        cands = pool[:TOPK]

        mgx, mgy = max(MARGIN * ww, 0.005), max(MARGIN * hh, 0.005)
        rect = (x - mgx, y - mgy, x + ww + mgx, y + hh + mgy)
        crop = None
        if cam.get("pyr"):                          # full-res available -> pull from the pyramid
            try:
                crop = dzi_region(cam["pyr"], *rect, self.fetch)
            except Exception:
                crop = None
        if crop is None:                            # small pano or pyramid miss -> downscaled full
            pano = self.fetch(cam["full"])
            W, H = pano.size
            crop = pano.crop((max(0, int(rect[0] * W)), max(0, int(rect[1] * H)),
                              min(W, int(rect[2] * W)), min(H, int(rect[3] * H))))
        fq = self.extract(crop, max_side=QUERY_MAXSIDE)

        items, matched = [], []
        for _, pid2, p in cands:
            try:
                fc = self.extract(self.fetch(p["full"]), key=p["full"], boxes=p.get("anon"))
            except Exception:
                continue
            mm, mask = self.match(fq, fc)
            inl = int(mask.sum()) if mask is not None else 0
            items.append({"pid": pid2, "ll": p["ll"], "brg": p["brg"], "fc": fc,
                          "mm": mm, "mask": mask, "inl": inl})
            if inl >= MIN_INL and p["brg"] is not None:
                matched.append((p["ll"], p["brg"], inl))
        ts = [t for ll, br, _ in matched if (t := ray_t(cam["ll"], A, ll, br)) is not None and 30 < t < RAY_MAXKM * 1000]
        poi = None
        if ts:
            tmed = median(ts)
            latr = math.radians(cam["ll"][1])
            poi = (cam["ll"][0] + tmed * math.sin(math.radians(A)) / (111320 * math.cos(latr)),
                   cam["ll"][1] + tmed * math.cos(math.radians(A)) / 110540)
        return {"a": a, "cam": cam, "A": A, "mode": mode, "crop": fq[0],
                "fq": fq, "items": items, "matched": matched, "poi": poi, "aco": aco,
                "geocode_dist": (hav_m(aco, poi) if (aco and poi) else None),
                "ray_dist": (median(ts) if ts else None),
                "nearest": (min(hav_m(ll, poi) for ll, _, _ in matched) if (poi and matched) else None)}

    def pair(self, aid, pid, matcher="lightglue"):
        with self.lock:
            k = ("pair", aid, pid, matcher)
            if k not in self.case_cache:
                self.case_cache[k] = self._pair(aid, pid, matcher)
            return self.case_cache[k]

    def _loftr(self, crop, tpil):
        if self.loftr is None:
            self.loftr = KF.LoFTR(pretrained="outdoor").eval()

        def prep(pil):
            r = resz(pil, LOFTR_MAXSIDE)
            w, h = r.size
            r = r.crop((0, 0, w - w % 8, h - h % 8))
            g = np.asarray(r.convert("L")).astype("float32") / 255.0
            return np.asarray(r), torch.from_numpy(g)[None, None]
        a0, t0 = prep(crop)
        a1, t1 = prep(tpil)
        with torch.inference_mode():
            o = self.loftr({"image0": t0, "image1": t1})
        return (a0, o["keypoints0"].cpu().numpy(), a1, o["keypoints1"].cpu().numpy(),
                o["confidence"].cpu().numpy())

    def _mast3r(self, crop, tpil):
        if self._m3 is None:
            for p in (MAST3R_REPO, os.path.join(MAST3R_REPO, "dust3r"),
                      os.path.join(MAST3R_REPO, "dust3r", "croco")):
                if p not in sys.path:
                    sys.path.insert(0, p)
            from mast3r.model import AsymmetricMASt3R
            from mast3r.fast_nn import fast_reciprocal_NNs
            from dust3r.inference import inference
            from dust3r.utils.image import load_images
            self._m3 = AsymmetricMASt3R.from_pretrained(MAST3R_CKPT).eval()
            self._m3_fns = (inference, load_images, fast_reciprocal_NNs)
        import tempfile
        inference, load_images, frnn = self._m3_fns
        d = tempfile.mkdtemp()
        p0, p1 = os.path.join(d, "a.png"), os.path.join(d, "b.png")
        resz(crop, 1024).save(p0)
        resz(tpil, 1024).save(p1)
        images = load_images([p0, p1], size=512, verbose=False)
        out = inference([tuple(images)], self._m3, "cpu", batch_size=1, verbose=False)
        d1 = out["pred1"]["desc"].squeeze(0).detach()
        d2 = out["pred2"]["desc"].squeeze(0).detach()
        m0, m1 = frnn(d1, d2, subsample_or_initxy1=8, device="cpu")
        m0, m1 = np.asarray(m0), np.asarray(m1)
        c1, c2 = out["pred1"].get("desc_conf"), out["pred2"].get("desc_conf")
        if c1 is not None and c2 is not None and len(m0):
            c1 = c1.squeeze(0).cpu().numpy()
            c2 = c2.squeeze(0).cpu().numpy()
            conf = np.sqrt(c1[m0[:, 1], m0[:, 0]] * c2[m1[:, 1], m1[:, 0]])   # MASt3R desc confidence
        else:
            conf = np.ones(len(m0))
        v1 = out["view1"]["img"][0].permute(1, 2, 0).cpu().numpy()
        v2 = out["view2"]["img"][0].permute(1, 2, 0).cpu().numpy()
        img0 = ((v1 * 0.5 + 0.5) * 255).clip(0, 255).astype("uint8")
        img1 = ((v2 * 0.5 + 0.5) * 255).clip(0, 255).astype("uint8")
        return (img0, m0.astype(float), img1, m1.astype(float), conf)

    def _pair(self, aid, pid, matcher="lightglue"):
        a = self.anns.get(aid)
        if not a:
            return {"error": "annotation not found"}
        pano = self.photos[a["photo_id"]]
        tgt = self.photos.get(pid)
        if not tgt or not tgt["full"]:
            return {"error": "target photo not found"}
        x, y, ww, hh = self.rects[aid]
        mg = MARGIN
        rect = (x - mg * ww, y - mg * hh, x + ww + mg * ww, y + hh + mg * hh)
        crop = None
        if pano.get("pyr"):
            try:
                crop = dzi_region(pano["pyr"], *rect, self.fetch)
            except Exception:
                crop = None
        if crop is None:
            p = self.fetch(pano["full"])
            W, H = p.size
            crop = p.crop((max(0, int(rect[0] * W)), max(0, int(rect[1] * H)),
                           min(W, int(rect[2] * W)), min(H, int(rect[3] * H))))
        tpil = self.fetch(tgt["full"])
        if matcher == "loftr":
            img0, k0, img1, k1, sc = self._loftr(crop, tpil)
            mm = (np.stack([np.arange(len(k0)), np.arange(len(k0))], 1)
                  if len(k0) else np.zeros((0, 2), int))
        elif matcher == "mast3r":
            img0, k0, img1, k1, sc = self._mast3r(crop, tpil)
            mm = (np.stack([np.arange(len(k0)), np.arange(len(k0))], 1)
                  if len(k0) else np.zeros((0, 2), int))
        else:
            f0 = self.extract(crop, max_side=QUERY_MAXSIDE)
            f1 = self.extract(tpil, boxes=tgt.get("anon"), max_side=QUERY_MAXSIDE)
            img0, img1 = f0[0], f1[0]
            k0, k1 = f0[1].cpu().numpy(), f1[1].cpu().numpy()
            inp = {"image0": {"keypoints": f0[1][None], "descriptors": f0[2][None], "image_size": f0[3][None]},
                   "image1": {"keypoints": f1[1][None], "descriptors": f1[2][None], "image_size": f1[3][None]}}
            with torch.inference_mode():
                out = self.lg(inp)
            mm = out["matches"][0].cpu().numpy()
            try:
                sc = out["scores"][0].cpu().numpy()
            except Exception:
                sc = np.ones(len(mm))
        mask, fin = None, 0
        if len(mm) >= 8:
            _, m = cv2.findFundamentalMat(k0[mm[:, 0]], k1[mm[:, 1]], cv2.FM_RANSAC, 3.0, 0.99)
            if m is not None:
                mask = m.ravel().astype(bool)
                fin = int(mask.sum())
        return {"a": a, "tgt": tgt, "img0": img0, "img1": img1, "k0": k0, "k1": k1,
                "mm": mm, "sc": np.asarray(sc), "mask": mask, "fin": fin, "raw": len(mm),
                "matcher": matcher}

    def _in_pie(self, C, L, slack=VIEW_SLACK):
        """Does L fall inside photo C's view-pie (bearing ±VIEW_HALF, range ≈ far×slack)?
        A photo can only see L if its view depth reaches L: distance(C,L) <= far×slack."""
        if C["brg"] is None:
            return False
        d = hav_m(C["ll"], L)
        far = (C.get("far") or FAR_DEFAULT) * slack
        return 5 < d <= far and abs(angn(brng(C["ll"], L) - C["brg"])) <= VIEW_HALF

    def _pie_ray(self, C, P, A, maxd, slack=VIEW_SLACK):
        """Does C's view-pie cross the pano ray, viewed from the pano's side?"""
        mlon = 111320 * math.cos(math.radians(P[1]))
        for d in range(300, int(maxd) + 1, 500):
            L = (P[0] + d * math.sin(math.radians(A)) / mlon,
                 P[1] + d * math.cos(math.radians(A)) / 110540)
            if self._in_pie(C, L, slack) and abs(angn(brng(C["ll"], L) - A)) <= SAME_SIDE:
                return True
        return False

    def case_geo(self, aid, limit=150, slack=VIEW_SLACK):
        a = self.anns.get(aid)
        if not a or aid not in self.rects:
            return None
        pano = self.photos[a["photo_id"]]
        x, y, ww, hh = self.rects[aid]
        cx = x + ww / 2
        fit = self.fits.get(a["photo_id"])
        A = ((pano["brg"] + fit[0] + fit[1] * cx) % 360) if (fit and pano["brg"] is not None) else pano["brg"]
        aco = (float(a["lon"]), float(a["lat"])) if a["lat"] else None
        cands = []
        if aco is not None:                       # view-pie contains geocode AND views it from pano's side
            aref = A if A is not None else brng(pano["ll"], aco)
            for pid2, p in self.photos.items():
                if pid2 == a["photo_id"] or not p["full"] or p["brg"] is None:
                    continue
                if self._in_pie(p, aco, slack) and abs(angn(brng(p["ll"], aco) - aref)) <= SAME_SIDE:
                    cands.append((abs(angn(brng(p["ll"], aco) - p["brg"])), hav_m(p["ll"], aco), pid2, p))
            cands.sort(key=lambda t: t[1])      # nearest to the POI first — close-ups are the meaningful ones
        elif A is not None:                       # no geocode: view-pie crosses the calibrated ray
            maxd = (pano.get("far") or FAR_DEFAULT) * slack
            for pid2, p in self.photos.items():
                if pid2 == a["photo_id"] or not p["full"] or p["brg"] is None:
                    continue
                if self._pie_ray(p, pano["ll"], A, maxd, slack):
                    cands.append((0.0, hav_m(pano["ll"], p["ll"]), pid2, p))
            cands.sort(key=lambda t: t[1])
        return {"a": a, "pano": pano, "A": A, "aco": aco,
                "cands": cands[:limit], "total": len(cands)}


def kp_img(rgb, kpts):
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR).copy()
    for kx, ky in kpts.cpu().numpy():
        cv2.circle(img, (int(kx), int(ky)), 2, (0, 200, 255), -1)
    return jb64(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def match_img(rgb0, kp0, rgb1, kp1, mm, mask, only_inliers):
    h = max(rgb0.shape[0], rgb1.shape[0])
    cvn = np.zeros((h, rgb0.shape[1] + rgb1.shape[1], 3), "uint8")
    cvn[:rgb0.shape[0], :rgb0.shape[1]] = rgb0
    cvn[:rgb1.shape[0], rgb0.shape[1]:] = rgb1
    bg = cv2.cvtColor(cvn, cv2.COLOR_RGB2BGR)
    off = rgb0.shape[1]
    k0, k1 = kp0.cpu().numpy(), kp1.cpu().numpy()
    for j, (i0, i1) in enumerate(mm):
        ok = mask is None or mask[j]
        if only_inliers and not ok:
            continue
        col = (0, 200, 0) if ok else (40, 40, 220)
        cv2.line(bg, (int(k0[i0][0]), int(k0[i0][1])),
                 (int(k1[i1][0]) + off, int(k1[i1][1])), col, 1)
    return jb64(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB))


def tri_map(P, A, matched, poi, aco):
    """Leaflet map of the triangulation in real coords (pano, calibrated ray,
    matched photos + bearing-rays, triangulated POI, geocode + ray-miss)."""
    latr = math.radians(P[1])
    mlon, mlat = 111320 * math.cos(latr), 110540
    tm = lambda ll: ((ll[0] - P[0]) * mlon, (ll[1] - P[1]) * mlat)
    sinA, cosA = math.sin(math.radians(A)), math.cos(math.radians(A))

    def dest(o, az, d):   # from (lon,lat) along azimuth, d metres -> [lat, lon]
        return [round(o[1] + d * math.cos(math.radians(az)) / 110540, 6),
                round(o[0] + d * math.sin(math.radians(az)) / (111320 * math.cos(math.radians(o[1]))), 6)]
    geo = lambda ll: [round(ll[1], 6), round(ll[0], 6)]
    dists = [math.hypot(*tm(ll)) for ll, _, _ in matched]
    if poi:
        dists.append(math.hypot(*tm(poi)))
    if aco:
        dists.append(math.hypot(*tm(aco)))
    raylen = (max(dists) if dists else 4000) * 1.3 + 300
    cam = geo(P)
    pts = [cam, dest(P, A, raylen)]
    j = [f"var cam={cam};",
         f"L.circleMarker(cam,{{color:'#000',radius:6,fillOpacity:1}}).addTo(map).bindTooltip('pano camera',{{permanent:true}});",
         f"L.polyline([cam,{dest(P, A, raylen)}],{{color:'#777',dashArray:'6 6'}}).addTo(map).bindTooltip('calibrated ray az {A:.0f}°');"]
    for ll, br, inl in matched:
        g = geo(ll)
        pts.append(g)
        j.append(f"L.circleMarker({g},{{color:'#0a0',radius:4,fillOpacity:1}}).addTo(map).bindTooltip('matched {inl} inl');")
        j.append(f"L.polyline([{g},{dest(ll, br, raylen)}],{{color:'#3a9',weight:1}}).addTo(map);")
    if poi:
        g = geo(poi)
        pts.append(g)
        j.append(f"L.circleMarker({g},{{color:'#d00',radius:7,fillOpacity:1}}).addTo(map).bindTooltip('triangulated POI',{{permanent:true}});")
    if aco:
        g = geo(aco)
        pts.append(g)
        qx, qy = tm(aco)
        along, miss = qx * sinA + qy * cosA, abs(qx * cosA - qy * sinA)
        j.append(f"L.circleMarker({g},{{color:'#06c',radius:6,fillOpacity:1}}).addTo(map).bindTooltip('geocode — ray miss {miss:.0f} m',{{permanent:true}});")
        j.append(f"L.polyline([{g},{dest(P, A, along)}],{{color:'#06c',dashArray:'2 4',weight:1}}).addTo(map);")
    j.append(f"map.fitBounds({pts},{{padding:[30,30]}});")
    return ("<div id='trimap' style='height:540px;border:1px solid #ccc'></div>"
            "<script>var map=L.map('trimap');"
            "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',"
            "{maxZoom:19,attribution:'\\u00a9 OpenStreetMap'}).addTo(map);"
            + "".join(j) + "</script>")


def case_map(aid, P, A, aco, cands):
    geo = lambda ll: [round(ll[1], 6), round(ll[0], 6)]

    def dest(o, az, d):
        return [round(o[1] + d * math.cos(math.radians(az)) / 110540, 6),
                round(o[0] + d * math.sin(math.radians(az)) / (111320 * math.cos(math.radians(o[1]))), 6)]
    cam = geo(P)
    pts = [cam]
    j = [f"var cam={cam};",
         f"L.circleMarker(cam,{{color:'#000',radius:7,fillOpacity:1}}).addTo(map).bindTooltip('pano camera',{{permanent:true}});"]
    if A is not None:
        re = dest(P, A, hav_m(P, aco) * 1.4 if aco else 8000)
        pts.append(re)
        j.append(f"L.polyline([cam,{re}],{{color:'#777',dashArray:'6 6'}}).addTo(map).bindTooltip('calibrated ray az {A:.0f}°');")
    if aco:
        g = geo(aco)
        pts.append(g)
        j.append(f"L.circleMarker({g},{{color:'#06c',radius:6,fillOpacity:1}}).addTo(map).bindTooltip('geocode',{{permanent:true}});")
    for db, d, pid2, p in cands:
        g = geo(p["ll"])
        pts.append(g)
        far = p.get("far")
        thumb = f"<br><img src='{p['t640']}' style='max-width:240px'>" if p.get("t640") else ""
        pop = (f"<b>{pid2[:8]}</b> · {(p.get('desc') or '')[:36]}<br>"
               f"dist {d/1000:.1f} km · aim {db:.0f}° off · sees~{(far/1000 if far else 0):.1f} km<br>"
               f"<a href='/pair/{aid}/{pid2}?m=mast3r' target=_blank>match (mast3r)</a> · "
               f"<a href='https://hillview.cz/?photo=hillview-{pid2}' target=_blank>hillview</a>{thumb}")
        j.append(f"L.circleMarker({g},{{color:'#0a7',radius:4,fillOpacity:.9}}).addTo(map).bindPopup({json.dumps(pop)},{{maxWidth:260}});")
        j.append(f"L.polyline([{g},{dest(p['ll'], p['brg'], min((far or 1500), 4000))}],{{color:'#0a7',weight:1.5,opacity:.5}}).addTo(map);")
    j.append(f"map.fitBounds({pts},{{padding:[30,30]}});")
    return ("<div id='trimap' style='height:560px;border:1px solid #ccc'></div>"
            "<script>var map=L.map('trimap');"
            "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',"
            "{maxZoom:19,attribution:'\\u00a9 OpenStreetMap'}).addTo(map);"
            + "".join(j) + "</script>")


app = Flask(__name__)
ENG = None


STUDIED_PAIRS = [
    ("67c6c4b9", "4b8cac8a", "TRUE ✓", "351/558 = 63%"),
    ("67c6c4b9", "d0955198", "false", "80/211 = 38%"),
    ("67c6c4b9", "b6d0d53b", "false (Doppelganger)", "32/82 = 39%"),
    ("67c6c4b9", "6bd93bf6", "unconfirmed", "33/62 = 53%"),
    ("67c6c4b9", "5acaf5ba", "true-neg", "0/6"),
    ("67c6c4b9", "f37ddd41", "true-neg", "~0"),
]


@app.route("/")
def index():
    srows = "".join(
        f'<tr><td>{v}</td><td>{rt}</td>'
        f'<td><a href="/pair/{an}/{ph}?m=mast3r">mast3r</a> · '
        f'<a href="/pair/{an}/{ph}">lightglue</a></td>'
        f'<td><small style=color:#999>{an}×{ph}</small></td></tr>'
        for an, ph, v, rt in STUDIED_PAIRS)
    panos = ""
    for pid in sorted(ENG.by_pano, key=lambda p: -len(ENG.by_pano[p])):
        cam = ENG.photos.get(pid, {})
        cal = "cal" if pid in ENG.fits else "—"
        lis = ""
        for a in ENG.by_pano[pid]:
            if a["ann_id"] not in ENG.rects:
                continue
            if "oops" in (a["body"] or "").lower():   # stitching-error markers, not real targets
                continue
            tag = "geo" if a["lat"] else ("ray" if pid in ENG.fits else "—")
            lis += f'<a href="/case/{a["ann_id"]}">{(a["body"][:34] or "(?)")} <small style="color:#999">[{tag}]</small></a> '
        panos += f'<h4>{pid[:8]} <small>{cal} · {cam.get("desc", "")[:46]}</small></h4>{lis}'
    ex = f"/pair/{STUDIED_PAIRS[0][0]}/{STUDIED_PAIRS[0][1]}?m=mast3r" if STUDIED_PAIRS else "#"
    return f"""<!doctype html><meta charset=utf-8><title>Hillview vision inspector</title>
<style>
body{{font:14px/1.5 system-ui;margin:0;color:#222}}
.wrap{{max-width:1060px;margin:0 auto;padding:22px}}
a{{color:#06c;text-decoration:none}} a:hover{{text-decoration:underline}}
td,th{{padding:3px 9px;border-bottom:1px solid #eee;text-align:left}}
h2{{margin:0 0 2px}} h3{{margin:24px 0 6px;border-bottom:2px solid #eee;padding-bottom:3px}}
h4{{margin:14px 0 4px}}
.card{{background:#f6f8fa;border:1px solid #e2e6ea;border-radius:8px;padding:10px 16px;margin:10px 0}}
.muted{{color:#888}} .big{{font-size:16px;font-weight:600}}
.legend{{font-size:12px;color:#777}} .legend b{{color:#555}}
</style>
<div class=wrap>
<h2>Hillview vision / enrichment inspector</h2>
<p class=muted>Two halves of one goal — <b>identify &amp; locate the distant features in photos</b>
(towers, hills, churches): the local-3D reconstruction that grounds it, and the annotation-matching
tools. Background: <code>docs/vision-subsystem.md</code> · <code>reconstruction-field-notes.md</code>.</p>

<h3>① Reconstruction — &ldquo;model the world bit by bit&rdquo;</h3>
<div class=card>
<a href="/runs/" class=big>▸ MASt3R-SfM reconstruction runs &amp; reports</a>
<p class=muted style="margin:4px 0 0">Each run reconstructs a set of overlapping photos (a walk /
vantage) into camera poses + a 3D point cloud, checked against GPS. The per-run report walks the
pipeline frame-by-frame — <b>input → mask → depth → confidence</b> — plus a pair-connectivity matrix,
a GPS-vs-recovered track map, a 3D point-cloud viewer, and the correspondence-masking drop count.
This page also hosts the older <b>geocoding / calibration</b> reports.</p>
</div>

<h3>② Localization inspector — annotation matching</h3>
<p class=muted>The original task: draw a rectangle around a distant landmark on a panorama → find which
close-up photos show it, and where it is. Two views:</p>
<ul style="margin:4px 0">
<li><b><a href="{ex}">pair</a></b> — match one annotation crop against one photo. The working tool:
toggle <b>MASt3R / LightGlue / LoFTR</b> + a match-score slider, inspect inliers. MASt3R is the only
matcher that bridges a distant pano ↔ a close-up.</li>
<li><b>case</b> (click any pano label below) — one annotation's calibrated bearing-ray + geocoded
location on a map, with LightGlue candidate matching (known unreliable — kept for comparison).</li>
</ul>

<h4>Hand-studied MASt3R pairs</h4>
<p class=muted style="margin:2px 0">Manually verified cases. <b>Inlier ratio</b> (geometrically
consistent / all matches) separates better than raw count — true ≈63%, Doppelganger ≈38% — yet
pairwise matching still can't reject confident look-alikes, which is exactly why ① exists.</p>
<table><tr><th>verdict</th><th>inlier ratio</th><th>open</th><th>ids</th></tr>{srows}</table>
<form onsubmit="location.href='/pair/'+this.a.value+'/'+this.p.value+'?m=mast3r';return false" style="margin:8px 0">
<input name=a placeholder="annotation id" size=16> &times;
<input name=p placeholder="photo id" size=16> <button>open mast3r pair</button></form>

<h4>Panos &amp; annotations <span class=muted>— click a label to open its case</span></h4>
<p class=legend>tags: <b>[geo]</b> geocoded anchor · <b>[ray]</b> calibrated bearing-ray only ·
<b>[cal]</b> pano has bearing calibration · <b>[—]</b> none</p>
{panos}
</div>"""


RUNS_DIR = os.path.join(HERE, "runs")


@app.route("/runs/")
def runs_index():
    items = []
    for d in sorted(os.listdir(RUNS_DIR)) if os.path.isdir(RUNS_DIR) else []:
        rep = os.path.join(RUNS_DIR, d, "report.html")
        if os.path.isfile(rep):
            st = ""
            sp = os.path.join(RUNS_DIR, d, "stats.json")
            if os.path.isfile(sp):
                try:
                    s = json.load(open(sp))
                    st = (f' <small style=color:#888>{s.get("n")} imgs · '
                          f'med resid {s.get("med_resid", 0):.1f} m · {s.get("npts")} pts</small>')
                except Exception:
                    pass
            has_ply = (os.path.isfile(os.path.join(RUNS_DIR, d, "dense.ply")) or
                       os.path.isfile(os.path.join(RUNS_DIR, d, "points.ply")))
            v = f' · <a href="/runs/{d}/view">3D</a>' if has_ply else ""
            items.append(f'<li><a href="/runs/{d}/report.html">{d}</a>{v}{st}</li>')
    # standalone geocoding / calibration reports (top-level enrich dir, not under runs/)
    reps = []
    for fn in sorted(glob.glob(os.path.join(HERE, "*.html"))):
        b = os.path.basename(fn)
        reps.append(f'<li><a href="/report/{b}">{b}</a> '
                    f'<small style=color:#888>{os.path.getsize(fn)//1024} KB</small></li>')
    rep_html = ("<h2>Geocoding / calibration reports</h2><ul>" + "".join(reps) + "</ul>") if reps else ""
    return ("<!doctype html><meta charset=utf-8><title>recon runs</title>"
            "<style>body{font:14px system-ui;margin:20px}a{color:#06c}</style>"
            "<h2>MASt3R-SfM reconstruction runs</h2><ul>" + "".join(items) + "</ul>" +
            rep_html + "<p><a href='/'>← inspector</a></p>")


@app.route("/runs/<path:p>")
def runs_file(p):
    return send_from_directory(RUNS_DIR, p)


@app.route("/report/<name>")
def enrich_report(name):
    """Serve a standalone HTML report from the enrich dir (annotation_geocode, geocode_debug, …)."""
    if not name.endswith(".html") or "/" in name or not os.path.isfile(os.path.join(HERE, name)):
        abort(404)
    return send_from_directory(HERE, name)


VIEWER_HTML = """<!doctype html><html><head><meta charset=utf-8><title>__RUN__ · point cloud</title>
<style>body{margin:0;overflow:hidden;background:#0d0d0d}
#hud{position:absolute;top:8px;left:10px;color:#cdd;font:13px system-ui;text-shadow:0 0 4px #000}
#hud a{color:#7cf} input{vertical-align:middle}</style></head><body>
<div id=hud>__RUN__ · loading __PLYNAME__ …</div>
<script type="importmap">{"imports":{
"three":"https://unpkg.com/three@0.160.0/build/three.module.js",
"three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {PLYLoader} from 'three/addons/loaders/PLYLoader.js';
const PLY='__PLY__', RUN='__RUN__';
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth,innerHeight);document.body.appendChild(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(0x0d0d0d);
const cam=new THREE.PerspectiveCamera(60,innerWidth/innerHeight,0.001,1e6);
const ctrl=new OrbitControls(cam,renderer.domElement);ctrl.enableDamping=true;
let pts,mat;
new PLYLoader().load(PLY,g=>{
  g.computeBoundingBox();const c=new THREE.Vector3();g.boundingBox.getCenter(c);
  g.translate(-c.x,-c.y,-c.z);
  const sz=g.boundingBox.getSize(new THREE.Vector3()).length();
  mat=new THREE.PointsMaterial({size:sz/1200,vertexColors:true,sizeAttenuation:true});
  pts=new THREE.Points(g,mat);scene.add(pts);
  cam.position.set(0,-sz*0.05,sz*0.55);cam.lookAt(0,0,0);ctrl.update();
  const n=g.attributes.position.count.toLocaleString();
  document.getElementById('hud').innerHTML=RUN+' · '+n+' pts · drag orbit, scroll zoom · '+
    'size <input id=sz type=range min=1 max=40 value=12 style=width:90px> · '+
    '<a href="/runs/">runs</a> <a href="/runs/'+RUN+'/report.html">report</a>';
  document.getElementById('sz').oninput=e=>{mat.size=sz/1200*(e.target.value/12)};
},undefined,err=>{document.getElementById('hud').textContent='failed to load '+PLY});
addEventListener('resize',()=>{cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();
  renderer.setSize(innerWidth,innerHeight)});
(function loop(){requestAnimationFrame(loop);ctrl.update();renderer.render(scene,cam)})();
</script></body></html>"""


@app.route("/runs/<run>/view")
def runs_view(run):
    base = os.path.join(RUNS_DIR, run)
    ply = "dense.ply" if os.path.isfile(os.path.join(base, "dense.ply")) else "points.ply"
    if not os.path.isfile(os.path.join(base, ply)):
        abort(404)
    return (VIEWER_HTML.replace("__RUN__", run)
            .replace("__PLYNAME__", ply)
            .replace("__PLY__", f"/runs/{run}/{ply}"))


def crop_img(aid):
    """The annotation rectangle's crop (full-res via DZI pyramid), as a JPEG."""
    aid = next((k for k in ENG.anns if k.startswith(aid)), aid)
    a = ENG.anns.get(aid)
    if not a or aid not in ENG.rects:
        abort(404)
    cam = ENG.photos[a["photo_id"]]
    x, y, ww, hh = ENG.rects[aid]
    mgx, mgy = max(MARGIN * ww, 0.005), max(MARGIN * hh, 0.005)
    rect = (x - mgx, y - mgy, x + ww + mgx, y + hh + mgy)
    crop = None
    if cam.get("pyr"):
        try:
            crop = dzi_region(cam["pyr"], *rect, ENG.fetch)
        except Exception:
            crop = None
    if crop is None:
        pano = ENG.fetch(cam["full"]); W, H = pano.size
        crop = pano.crop((max(0, int(rect[0] * W)), max(0, int(rect[1] * H)),
                          min(W, int(rect[2] * W)), min(H, int(rect[3] * H))))
    w, h = crop.size; s = min(1.0, 900 / max(w, h))
    if s < 1:
        crop = crop.resize((max(1, int(w * s)), max(1, int(h * s))))
    buf = io.BytesIO(); crop.save(buf, "JPEG", quality=85)
    return Response(buf.getvalue(), mimetype="image/jpeg")


app.add_url_rule("/crop/<aid>", "crop_img", crop_img)


@app.route("/case/<aid>")
def case(aid):
    aid = next((k for k in ENG.anns if k.startswith(aid)), aid)
    slack = float(request.args.get("slack", VIEW_SLACK))
    g = ENG.case_geo(aid, int(request.args.get("n", 150)), slack)
    if not g:
        abort(404)
    a, pano = g["a"], g["pano"]
    themap = case_map(aid, pano["ll"], g["A"], g["aco"], g["cands"])
    def _cand(db, d, pid2, p):
        th = (f"<img src='{p['t640']}' style='max-width:150px;display:block;border:1px solid #ccc'>"
              if p.get("t640") else "<div style='width:150px;color:#999'>(no thumb)</div>")
        return (f"<div style='display:inline-block;margin:5px;text-align:center;vertical-align:top'>"
                f"<a href='/pair/{aid}/{pid2}?m=mast3r' target=_blank>{th}{pid2[:8]}</a>"
                f"<br><small style=color:#999>{d/1000:.1f}km · {db:.0f}°</small></div>")
    clist = "".join(_cand(*c) for c in g["cands"])
    mode = "geocoded POI" if g["aco"] else ("ray (no geocode)" if g["A"] is not None else "uncalibrated")
    return f"""<!doctype html><meta charset=utf-8>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{font:13px system-ui;margin:20px;max-width:1100px}}a{{color:#06c;text-decoration:none}}a:hover{{text-decoration:underline}}</style>
<a href="/">← directory</a><h2>{a["body"][:60]}</h2>
<p style=margin:0><b>annotation crop</b> (the target feature):</p>
<img src="/crop/{aid}" style="max-height:220px;border:2px solid #888" title="the rectangle drawn on the pano">
<p><b>pano</b> {a["photo_id"][:8]} — {pano.get("desc", "")[:60]} · {mode} · <b>{g["total"]}</b> view-pie candidates{f' (showing {len(g["cands"])} — add ?n=N for more)' if g["total"] > len(g["cands"]) else ''}</p>
<p style=color:#888>Candidate = photos whose <b>view-pie</b> (position + bearing ±{VIEW_HALF}° + range ≈ farthest_object × <b>{slack:g}</b>)
contains the POI <b>and views it from the pano's side</b> (within ±{SAME_SIDE}° of the ray → same face). A photo is dropped when its
claimed view depth can't reach the POI. The green line shows its facing (length ∝ how far it claims to see). Tune precision with
<code>?slack=N</code> (now {slack:g}; lower = stricter). Click a marker for a thumbnail, hillview link, and <b>match with MASt3R</b>.</p>
{themap}
<p style=margin-top:10px><b>candidates:</b> {clist or "(none)"}</p>"""


@app.route("/pair/<aid>/<pid>")
def pair(aid, pid):
    m = request.args.get("m", "lightglue")
    aid = next((k for k in ENG.anns if k.startswith(aid)), aid)
    pid = next((k for k in ENG.photos if k.startswith(pid)), pid)
    r = ENG.pair(aid, pid, m)
    if "error" in r:
        return f'<a href="/">back</a> · {r["error"]}'
    w0, h0 = r["img0"].shape[1], r["img0"].shape[0]
    w1 = r["img1"].shape[1]
    k0, k1, mm, sc, mask = r["k0"], r["k1"], r["mm"], r["sc"], r["mask"]
    order = list(np.argsort(-sc)[:800]) if len(mm) else []   # cap drawn lines (LoFTR is dense)
    lines = ""
    for j in order:
        i0, i1 = int(mm[j][0]), int(mm[j][1])
        inl = mask is not None and mask[j]
        lines += (f'<line x1="{k0[i0][0]:.0f}" y1="{k0[i0][1]:.0f}" '
                  f'x2="{k1[i1][0] + w0:.0f}" y2="{k1[i1][1]:.0f}" '
                  f'class="m {"in" if inl else "out"}" data-s="{float(sc[j]):.3f}"/>')
    a, tgt = r["a"], r["tgt"]
    geom = ""
    if a["lat"] and tgt["brg"] is not None:
        poi = (float(a["lon"]), float(a["lat"]))
        geom = (f' · target {hav_m(poi, tgt["ll"]):.0f} m from POI, '
                f'aimed {abs(angn(brng(tgt["ll"], poi) - tgt["brg"])):.0f}° off')
    links = " · ".join((f'<b>{mt}</b>' if mt == r["matcher"] else f'<a href="?m={mt}">{mt}</a>')
                       for mt in ("lightglue", "loftr", "mast3r"))
    drawn = f' (showing top {len(order)})' if len(mm) > len(order) else ''
    ratio = 100 * r["fin"] / r["raw"] if r["raw"] else 0
    pdesc = ENG.photos.get(a["photo_id"], {}).get("desc", "")
    tdesc = tgt.get("desc", "")
    H = max(h0, r["img1"].shape[0])
    return f"""<!doctype html><meta charset=utf-8>
<style>body{{font:13px system-ui;margin:14px}}
#wrap{{position:relative;width:{w0 + w1}px}} #wrap img{{vertical-align:top}}
svg{{position:absolute;top:0;left:0;pointer-events:none}}
line.m{{stroke:#999;stroke-width:1;opacity:.45;pointer-events:stroke;cursor:pointer}}
line.m.in{{stroke:#0a0;opacity:.85}} line.m:hover{{stroke:#e00;stroke-width:3;opacity:1}}
line.m.pin{{stroke:#e00;stroke-width:3;opacity:1}} line.m.hide{{display:none}}
.ctl{{margin:8px 0}}</style>
<a href="/">all cases</a>
<h3>{a["body"][:50]}</h3>
<p><a href="/">← directory</a> · <b>pano</b> {a["photo_id"][:8]} — {pdesc[:46]} &nbsp;&times;&nbsp; <b>target</b> {pid[:8]} — {tdesc[:40]}</p>
<p>matcher: {links} · raw <b>{r["raw"]}</b>{drawn} · F-inliers <b>{r["fin"]}</b> · <b>ratio {ratio:.0f}%</b>{geom}</p>
<div class=ctl>min score <input id=sl type=range min=0 max=1 step=0.01 value=0 oninput=upd()>
<span id=sv>0.00</span> · <label><input id=io type=checkbox onchange=upd()> inliers only</label>
· hover a line to highlight, click to pin</div>
<div id=wrap><img src="{jb64(r['img0'])}"><img src="{jb64(r['img1'])}">
<svg width="{w0 + w1}" height="{H}">{lines}</svg></div>
<script>
const ls=[...document.querySelectorAll('line.m')];
ls.forEach(l=>l.addEventListener('click',()=>l.classList.toggle('pin')));
function upd(){{const mn=parseFloat(sl.value);sv.textContent=mn.toFixed(2);const io_=io.checked;
ls.forEach(l=>{{const s=parseFloat(l.dataset.s),inl=l.classList.contains('in');
l.classList.toggle('hide',(s<mn||(io_&&!inl))&&!l.classList.contains('pin'));}});}}
</script>"""


if __name__ == "__main__":
    ENG = Engine()
    # 8766: caddy now owns 8765 (fronts the enrich workbench for the ygg address)
    app.run(host="0.0.0.0", port=int(os.environ.get("VIZ_PORT", 8766)), threaded=True)
