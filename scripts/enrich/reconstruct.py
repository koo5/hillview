#!/usr/bin/env python3
"""
reconstruct — MASt3R-SfM on a dense local cluster ("a bit of the world").

Selects a contiguous (capture-time-ordered) slice of close-range photos from a
DB dump, downloads them, runs MASt3R sparse global alignment (forward pass ->
matching -> 3D optim -> 2D refine -> triangulation), and writes:
  - scene.npz       camera poses, intrinsics, sparse points, colors
  - points.ply      sparse colored point cloud (open in any 3D viewer)
  - report.html     Leaflet map: RECOVERED camera track (Umeyama-aligned to GPS)
                    vs GPS, plus a top-down point-cloud render and residual stats

The point: if a dozen overlapping street shots reconstruct into ONE consistent
local model whose recovered camera track matches GPS to a few metres, the
"model the world bit by bit" path is tractable -- and Doppelgangers can't
survive a globally consistent reconstruction.

  .venv/bin/python reconstruct.py --n 8 --win 3 --out runs/recon_s0
"""
import argparse, base64, csv, glob, io, json, math, os, sys, time, urllib.request
import numpy as np
from PIL import Image

csv.field_size_limit(10**9)
HERE = os.path.dirname(os.path.abspath(__file__))
MAST3R_REPO = os.path.join(HERE, "mast3r_repo")
MAST3R_CKPT = os.path.join(MAST3R_REPO, "checkpoints", "mast3r.pth")
DUMP_DIR = "/shared/dbdump"
PHOTOS_CSV = None  # explicit photos-CSV path override (set from --photos_csv)


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


# ---------- data ----------
def latest_csv(stem, d=DUMP_DIR):
    if stem == "photos" and PHOTOS_CSV:
        return PHOTOS_CSV
    c = sorted(glob.glob(os.path.join(d, stem + "*.csv")))
    if not c:
        raise SystemExit(f"no {stem}*.csv in {d}")
    return c[-1]


def wkt(g):
    if g and g.upper().startswith("POINT"):
        lo, la = g[g.index("(") + 1:g.index(")")].split()
        return float(lo), float(la)
    return None


BLUR_CONFIDENCE = 0.4  # mirrors backend/worker/detections.py: blurred iff conf is None or >= this


def parse_anon(r):
    """Boxes that were actually BLURRED/anonymized (cars, people, …), (x1,y1,x2,y2) in original px.
    Mirrors the worker's should_blur(): a detection is blurred iff it has no confidence
    (manual override / old format) or confidence >= BLUR_CONFIDENCE. Sub-threshold detections
    (recorded but left visible in the image) are NOT masked."""
    try:
        d = json.loads(r.get("detected_objects") or "{}")
    except Exception:
        return []
    out = []
    for o in (d.get("objects") or []):
        b = o.get("bbox") or {}
        if not all(k in b for k in ("x1", "y1", "x2", "y2")):
            continue
        conf = o.get("confidence")
        # prefer the persisted "blurred" flag (worker formats #2/#3); fall back to
        # should_blur for older records (#1 / #1b) — see backend/worker/detections.py
        if o.get("blurred", conf is None or conf >= BLUR_CONFIDENCE):
            out.append((b["x1"], b["y1"], b["x2"], b["y2"]))
    return out


def fetch(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "hillview-recon/0.1"})
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=90).read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.5)


def select_cluster(center, radius_m, n, start, maxscan, stride=1, after="", before=""):
    """Read dump, return contiguous capture-time slice within radius of center."""
    lat0, lon0 = center
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    rows = []
    path = latest_csv("photos")
    log(f"scanning {path}")
    for r in csv.DictReader(open(path)):
        if r.get("processing_status") != "completed":
            continue
        if str(r.get("deleted")).lower() in ("t", "true", "1"):
            continue
        ll = wkt(r.get("geometry"))
        if not ll:
            continue
        lon, lat = ll
        e = (lon - lon0) * kx
        nth = (lat - lat0) * ky
        d = math.hypot(e, nth)
        if d > radius_m:
            continue
        cap = (r.get("captured_at") or "")[:19]
        if after and cap < after:
            continue
        if before and cap > before:
            continue
        try:
            s = json.loads(r["sizes"])
        except Exception:
            continue
        full = (s.get("full") or {})
        url = full.get("url")
        if not url:
            continue
        t640 = ((s.get("thumb_640") or s.get("640") or {}) or {}).get("url")
        rows.append({
            "id": r["id"], "lat": lat, "lon": lon,
            "e": e, "n": nth, "d": d,
            "alt": float(r["altitude"]) if r.get("altitude") else None,
            "brg": float(r["compass_angle"]) if r.get("compass_angle") else None,
            "cap": r.get("captured_at") or r.get("uploaded_at") or "",
            "full": url, "t640": t640,
            "ttl": (r.get("title") or "")[:60],
            "anon": parse_anon(r), "ow": int(r["width"]), "oh": int(r["height"]),
            "ofn": r.get("original_filename") or "",
        })
        if maxscan and len(rows) >= maxscan:
            pass  # keep scanning whole file; maxscan only caps memory if huge
    log(f"{len(rows)} photos within {radius_m}m of {lat0:.5f},{lon0:.5f}")
    rows.sort(key=lambda x: x["cap"])
    sub = rows[start:start + n * stride:stride]
    log(f"selected slice [{start}:{start+n}] -> {len(sub)} photos, "
        f"cap {sub[0]['cap'][:19] if sub else '-'} .. {sub[-1]['cap'][:19] if sub else '-'}")
    return sub


def fetch_by_ids(prefixes, center):
    """Fetch specific photos by id-prefix regardless of radius (for impostor injection)."""
    if not prefixes:
        return []
    lat0, lon0 = center
    kx = 111320.0 * math.cos(math.radians(lat0)); ky = 110540.0
    want = list(prefixes); found = {}
    for r in csv.DictReader(open(latest_csv("photos"))):
        for pre in want:
            if r["id"].startswith(pre) and pre not in found:
                ll = wkt(r.get("geometry"))
                try:
                    s = json.loads(r["sizes"])
                except Exception:
                    s = {}
                url = (s.get("full") or {}).get("url")
                if not (ll and url):
                    continue
                lon, lat = ll
                found[pre] = {
                    "id": r["id"], "lat": lat, "lon": lon,
                    "e": (lon - lon0) * kx, "n": (lat - lat0) * ky,
                    "d": math.hypot((lon - lon0) * kx, (lat - lat0) * ky),
                    "alt": float(r["altitude"]) if r.get("altitude") else None,
                    "brg": float(r["compass_angle"]) if r.get("compass_angle") else None,
                    "cap": r.get("captured_at") or "", "full": url, "t640": None, "inj": True,
                    "anon": parse_anon(r), "ow": int(r["width"]), "oh": int(r["height"]),
                    "ofn": r.get("original_filename") or "",
                    "ttl": "INJECTED:" + (r.get("title") or "")[:50],
                }
    miss = [p for p in want if p not in found]
    if miss:
        log(f"WARN injected ids not found: {miss}")
    return [found[p] for p in want if p in found]


SLC_DIR = "/shared/slc/sync"   # Solocator-synced originals (filename = capture timestamp)
_slc_set = None


def slc_basenames():
    global _slc_set
    if _slc_set is None:
        try:
            _slc_set = set(os.listdir(SLC_DIR))
        except Exception:
            _slc_set = set()
    return _slc_set


def green_overlay_mask(rgb):
    """rgb: uint8 (H,W,3). Bool mask of the neon-green Solocator marks (crosshair, tilt, corner
    texts), 2-px dilated. None if the overlay isn't present (a mode used on a subset of photos)."""
    a = rgb.astype(int)
    R, G, Bb = a[..., 0], a[..., 1], a[..., 2]
    green = (G > 140) & (R < 150) & (Bb < 150) & (G - R > 45) & (G - Bb > 45)
    if green.mean() < 0.0005:
        return None
    m = green.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            m |= np.roll(np.roll(green, dy, 0), dx, 1)
    return m


def crop_solocator_bar(img, top_frac=0.15):
    """If the Solocator overlay is present, CROP off the fixed top compass/GPS bar — cleaner
    than painting (removes the bar AND its boundary, no artificial edge for the matcher to grab).
    The green crosshair/tilt/text marks are handled by correspondence-level masking, not painted.
    Returns (image, did_crop)."""
    if green_overlay_mask(np.asarray(img)) is None:
        return img, False
    W, H = img.size
    return img.crop((0, int(H * top_frac), W, H)), True


# ---- correspondence-level masking (the principled way: exclude masked pixels from matching,
#      never paint — painting would add boundary features; cf. DynaSLAM, MASt3R mask_sky) ----
CORR_MASKS = {}   # {image instance/path: bool ndarray (H,W) at loaded res, True = drop matches}
CORR_STATS = {"dropped": 0, "total": 0}   # correspondences dropped by masking (for the report)


def save_mask_overlay(rgb, mask, path):
    """Eyeball view: the loaded frame with masked (dropped-from-matching) pixels tinted red."""
    out = rgb.copy()
    red = np.array([235, 40, 40], float)
    out[mask] = (0.40 * out[mask] + 0.60 * red).clip(0, 255).astype(np.uint8)
    Image.fromarray(out).save(path)


def map_box_to_loaded(box, W1, H1, size=512, patch=16):
    """Map a box (x1,y1,x2,y2) from saved-image px into the load_images(size) loaded frame —
    resize long side to `size`, then centre-crop to a multiple of `patch`. Returns
    ((bx1,by1,bx2,by2) clamped, (W2,H2))."""
    r = size / max(W1, H1)
    W, H = round(W1 * r), round(H1 * r)
    cx, cy = W // 2, H // 2
    halfw = ((2 * cx) // patch) * patch / 2
    halfh = ((2 * cy) // patch) * patch / 2
    cl, ct = cx - halfw, cy - halfh
    W2, H2 = int(2 * halfw), int(2 * halfh)
    x1, y1, x2, y2 = box
    return (max(0, int(x1 * r - cl)), max(0, int(y1 * r - ct)),
            min(W2, int(round(x2 * r - cl))), min(H2, int(round(y2 * r - ct)))), (W2, H2)


def install_corr_masking():
    """Wrap MASt3R-SfM's forward_mast3r so that, after correspondences are computed/cached, any
    correspondence whose endpoint falls in a CORR_MASKS region is dropped (no pixel painting)."""
    import mast3r.cloud_opt.sparse_ga as SGA
    if getattr(SGA, "_corr_mask_installed", False):
        return
    import torch as _t
    orig = SGA.forward_mast3r

    def patched(pairs, model, cache_path, desc_conf='desc_conf', device='cuda', subsample=8, **kw):
        out = orig(pairs, model, cache_path, desc_conf=desc_conf, device=device,
                   subsample=subsample, **kw)
        res_paths = out[0]   # forward_mast3r returns (res_paths_dict, cache_path)
        ndrop = ntot = 0
        for (i1, i2), ((p1, p2), pc) in res_paths.items():
            m1, m2 = CORR_MASKS.get(i1), CORR_MASKS.get(i2)
            if m1 is None and m2 is None:
                continue
            try:
                score, (xy1, xy2, confs) = _t.load(pc)
            except Exception:
                continue
            a1, a2 = np.asarray(xy1), np.asarray(xy2)
            keep = np.ones(len(a1), bool)
            for m, xy in ((m1, a1), (m2, a2)):
                if m is None:
                    continue
                H, W = m.shape
                x = np.clip(xy[:, 0].astype(int), 0, W - 1)
                y = np.clip(xy[:, 1].astype(int), 0, H - 1)
                keep &= ~m[y, x]
            ntot += len(keep); ndrop += int((~keep).sum())
            cf = confs[keep]
            _t.save(((score[0], float(cf.sum()), int(len(cf))), (xy1[keep], xy2[keep], cf)), pc)
        if ntot:
            CORR_STATS["dropped"] += ndrop; CORR_STATS["total"] += ntot
            log(f"  corr-mask: dropped {ndrop}/{ntot} correspondences landing in masked regions")
        return out

    SGA.forward_mast3r = patched
    SGA._corr_mask_installed = True


def download(sub, imgdir, mask_anon=False, mask_solocator=False):
    """Download (and for Solocator overlays, crop the top bar). No pixel painting — anon boxes
    are recorded in *saved-image* coords (`anon_saved`/`saved_wh`) for later correspondence-masking."""
    os.makedirs(imgdir, exist_ok=True)
    paths = []
    n_slc = 0
    n_anon = 0
    slc = slc_basenames() if mask_solocator else set()
    for i, p in enumerate(sub):
        fp = os.path.join(imgdir, f"{i:03d}_{p['id'][:8]}.jpg")
        if not os.path.exists(fp) or mask_anon or mask_solocator:
            log(f"  dl {i+1}/{len(sub)} {p['id'][:8]}")
            img = Image.open(io.BytesIO(fetch(p["full"]))).convert("RGB")
            Wf, Hf = img.size
            # anon boxes: original-image px -> full(downloaded) px
            asx, asy = Wf / max(p.get("ow", Wf), 1), Hf / max(p.get("oh", Hf), 1)
            aboxes = [(x1 * asx, y1 * asy, x2 * asx, y2 * asy) for (x1, y1, x2, y2) in (p.get("anon") or [])]
            crop_y = 0
            if mask_solocator and os.path.basename(p.get("ofn") or "") in slc:
                if green_overlay_mask(np.asarray(img)) is not None:
                    crop_y = int(Hf * 0.15)
                    img = img.crop((0, crop_y, Wf, Hf))   # drop the fixed top compass/GPS bar
                    n_slc += 1
            # record anon boxes in saved coords (shifted by any crop), for correspondence-masking
            p["anon_saved"] = [(x1, max(0.0, y1 - crop_y), x2, y2 - crop_y)
                               for (x1, y1, x2, y2) in aboxes if y2 - crop_y > 0]
            p["saved_wh"] = (Wf, Hf - crop_y)
            n_anon += len(p["anon_saved"])
            img.save(fp, "JPEG", quality=92)
        paths.append(fp)
        p["path"] = fp
    if mask_solocator:
        log(f"  cropped Solocator top bar on {n_slc}/{len(sub)} frame(s)")
    if mask_anon:
        log(f"  recorded {n_anon} anon box(es) for correspondence-masking (not painted)")
    return paths


# ---------- geometry ----------
def umeyama(src, dst):
    """Similarity transform (scale s, rot R, trans t) mapping src->dst (Nx3). Returns s,R,t."""
    src = np.asarray(src, float); dst = np.asarray(dst, float)
    mu_s = src.mean(0); mu_d = dst.mean(0)
    S = src - mu_s; D = dst - mu_d
    cov = (D.T @ S) / len(src)
    U, d, Vt = np.linalg.svd(cov)
    Sgn = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        Sgn[2, 2] = -1
    R = U @ Sgn @ Vt
    var_s = (S ** 2).sum() / len(src)
    s = np.trace(np.diag(d) @ Sgn) / var_s
    t = mu_d - s * R @ mu_s
    return s, R, t


def write_ply(path, pts, cols):
    pts = np.asarray(pts); cols = np.asarray(cols)
    cols = np.clip(cols * (255 if cols.max() <= 1.01 else 1), 0, 255).astype(np.uint8)
    with open(path, "w") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write(f"element vertex {len(pts)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write("property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for (x, y, z), (r, g, b) in zip(pts, cols):
            f.write(f"{x:.4f} {y:.4f} {z:.4f} {int(r)} {int(g)} {int(b)}\n")


def topdown_png(path, pts, cols, cams, size=900):
    """Top-down (X-Z) scatter of the point cloud + camera centers, via numpy/PIL."""
    pts = np.asarray(pts); cols = np.asarray(cols)
    if cols.max() <= 1.01:
        cols = (cols * 255)
    cols = np.clip(cols, 0, 255).astype(np.uint8)
    X = pts[:, 0]; Z = pts[:, 2]
    # robust bounds (2-98 pct)
    xlo, xhi = np.percentile(X, 2), np.percentile(X, 98)
    zlo, zhi = np.percentile(Z, 2), np.percentile(Z, 98)
    pad = 0.05 * max(xhi - xlo, zhi - zlo, 1e-6)
    xlo -= pad; xhi += pad; zlo -= pad; zhi += pad
    sx = (size - 1) / max(xhi - xlo, 1e-6); sz = (size - 1) / max(zhi - zlo, 1e-6)
    sc = min(sx, sz)
    canvas = np.zeros((size, size, 3), np.uint8)
    px = ((X - xlo) * sc).astype(int); pz = ((Z - zlo) * sc).astype(int)
    ok = (px >= 0) & (px < size) & (pz >= 0) & (pz < size)
    canvas[size - 1 - pz[ok], px[ok]] = cols[ok]
    img = Image.fromarray(canvas)
    # draw cameras as red squares
    from PIL import ImageDraw
    dr = ImageDraw.Draw(img)
    for c in cams:
        cx = int((c[0] - xlo) * sc); cz = int((c[2] - zlo) * sc)
        cy = size - 1 - cz
        dr.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], outline=(255, 60, 60), width=2)
    img.save(path)


def render_depth(depth, path):
    """Colormap a per-frame depthmap: near = red (hot), far = blue (cold), invalid = black."""
    d = np.asarray(depth, float)
    valid = np.isfinite(d) & (d > 0)
    if not valid.any():
        return False
    lo, hi = np.percentile(d[valid], 2), np.percentile(d[valid], 98)
    n = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)        # 0 = nearest, 1 = farthest
    H = (n * 0.66 * 255).astype(np.uint8)                   # hue 0(red)->0.66(blue)
    S = np.full(d.shape, 230, np.uint8)
    V = np.where(valid, 255, 0).astype(np.uint8)
    Image.fromarray(np.stack([H, S, V], -1), "HSV").convert("RGB").save(path)
    return True


def render_conf(conf, path):
    """Colormap a per-frame MASt3R confidence map (log-scaled): low = dark violet, high = yellow.
    This is the pointmap confidence that gates the dense cloud — bright where the model is sure."""
    c = np.log1p(np.clip(np.asarray(conf, float), 0, None))
    lo, hi = np.percentile(c, 2), np.percentile(c, 98)
    n = np.clip((c - lo) / max(hi - lo, 1e-6), 0, 1)
    H = ((0.75 - 0.6 * n) * 255).astype(np.uint8)           # violet(low)->yellow(high)
    S = np.full(c.shape, 200, np.uint8)
    V = (55 + 200 * n).clip(0, 255).astype(np.uint8)
    Image.fromarray(np.stack([H, S, V], -1), "HSV").convert("RGB").save(path)


def pair_count_matrix(cache_path, paths):
    """Read the per-pair correspondence counts (post-masking) from the corres cache → N×N matrix."""
    import glob as _g
    import torch as _t
    try:
        from mast3r.utils.misc import hash_md5
    except Exception:
        from dust3r.utils.misc import hash_md5
    n = len(paths)
    h2i = {hash_md5(p): i for i, p in enumerate(paths)}
    mat = np.zeros((n, n), int)
    for f in _g.glob(os.path.join(cache_path, "corres_conf=*", "*.pth")):
        name = os.path.splitext(os.path.basename(f))[0]
        if "-" not in name:
            continue
        h1, h2 = name.split("-", 1)
        if h1 in h2i and h2 in h2i:
            try:
                score, _ = _t.load(f, map_location="cpu")
            except Exception:
                continue
            mat[h2i[h1], h2i[h2]] = int(score[2])
    return mat


def render_pair_matrix(mat, path, target=620):
    """N×N correspondence-count heatmap (symmetrized): bright = many matches, dark = none."""
    m = (mat + mat.T).astype(float)
    n = m.shape[0]
    mx = m.max() or 1.0
    norm = np.sqrt(m / mx)                                   # sqrt to lift mid-range
    H = ((0.66 * (1 - norm)) * 255).astype(np.uint8)         # blue(few)->red(many)
    S = np.full(m.shape, 220, np.uint8)
    V = np.where(m > 0, (60 + 195 * norm).clip(0, 255), 25).astype(np.uint8)
    img = Image.fromarray(np.stack([H, S, V], -1), "HSV").convert("RGB")
    scale = max(1, target // max(n, 1))
    img.resize((n * scale, n * scale), Image.NEAREST).save(path)


# ---------- report ----------
def enu_to_ll(e, n, lat0, lon0):
    kx = 111320.0 * math.cos(math.radians(lat0)); ky = 110540.0
    return lat0 + n / ky, lon0 + e / kx


def report_html(out, sub, center, cam_ll_gps, cam_ll_rec, resid, stats):
    lat0, lon0 = center
    def mk(arr, color, label):
        pts = ",".join(f"[{la:.6f},{lo:.6f}]" for la, lo in arr)
        return pts
    gps_js = "[" + ",".join(f"[{la:.6f},{lo:.6f}]" for la, lo in cam_ll_gps) + "]"
    rec_js = "[" + ",".join(f"[{la:.6f},{lo:.6f}]" for la, lo in cam_ll_rec) + "]"
    ids = json.dumps([p["id"][:8] for p in sub])
    resid_js = json.dumps([round(float(x), 1) for x in resid])
    def _hv(i, p):
        la, lo = cam_ll_gps[i]
        b = p['brg'] if p['brg'] is not None else 0
        return (f"https://hillview.cz/?photo=hillview-{p['id']}"
                f"&lat={la:.7f}&lon={lo:.7f}&zoom=20&bearing={b}")
    has_depth = any(os.path.exists(os.path.join(out, f"depth_{i:03d}_{p['id'][:8]}.png"))
                    for i, p in enumerate(sub))
    has_mask = any(os.path.exists(os.path.join(out, f"mask_{i:03d}_{p['id'][:8]}.png"))
                   for i, p in enumerate(sub))
    has_conf = any(os.path.exists(os.path.join(out, f"conf_{i:03d}_{p['id'][:8]}.png"))
                   for i, p in enumerate(sub))
    def _col(prefix, i, p, title, show):
        if not show:
            return ""
        fn = f"{prefix}_{i:03d}_{p['id'][:8]}.png"
        return (f"<td><img class=thumb src='{fn}' title='{title}'></td>"
                if os.path.exists(os.path.join(out, fn)) else "<td>—</td>")
    rows = "".join(
        f"<tr><td>{i}</td>"
        f"<td><a href='{_hv(i,p)}' target=_blank title='open on hillview.cz (cross-check location/bearing)'>"
        f"<img class=thumb src='imgs/{i:03d}_{p['id'][:8]}.jpg' loading=lazy></a></td>"
        f"{_col('mask', i, p, 'red = pixels dropped from matching', has_mask)}"
        f"{_col('depth', i, p, 'near=red far=blue', has_depth)}"
        f"{_col('conf', i, p, 'MASt3R confidence: violet=low yellow=high', has_conf)}"
        f"<td><a href='{_hv(i,p)}' target=_blank>{p['id'][:8]} ↗</a><br>"
        f"<a href='imgs/{i:03d}_{p['id'][:8]}.jpg' target=_blank style='font-size:11px'>input img</a></td>"
        f"<td>{p['cap'][:19]}</td>"
        f"<td>{p['brg'] if p['brg'] is not None else '-'}</td>"
        f"<td>{resid[i]:.1f} m</td><td>{p['ttl']}</td></tr>"
        for i, p in enumerate(sub))
    td_png = os.path.basename(stats["topdown"]) if stats.get("topdown") else ""
    ps = stats.get("pair_stats") or {}
    pmat_html = ""
    if os.path.exists(os.path.join(out, "pairs_matrix.png")) and ps:
        iso = ps.get("isolated") or []
        pmat_html = (
            f'<div style="margin-top:10px"><b>Pair connectivity</b> '
            f'<small style="color:#888">(post-masking correspondence counts; row/col = frame #, '
            f'bright=many matches, dark=no overlap)</small><br>'
            f'<img src="pairs_matrix.png" title="correspondences per pair">'
            f'<div style="font-size:13px"><span class=k>{ps.get("connected_pairs",0)}</span> connected pairs · '
            f'median <span class=k>{ps.get("median_matches",0)}</span> matches/pair · '
            f'weakest <span class=k>{ps.get("min_matches",0)}</span>'
            f'{(" · <span style=color:#f88>isolated: " + ", ".join(iso) + "</span>") if iso else " · no isolated frames"}'
            f'</div></div>')
    html = f"""<!doctype html><meta charset=utf-8>
<title>MASt3R-SfM recon — {stats['n']} imgs</title>
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{font:14px system-ui;margin:0;background:#111;color:#ddd}}
#map{{height:62vh}} .wrap{{padding:14px 20px}}
table{{border-collapse:collapse;font-size:13px}} td,th{{border:1px solid #333;padding:3px 7px}}
.k{{color:#9cf}} .big{{font-size:22px;font-weight:600}} img{{max-width:46%;vertical-align:top;border:1px solid #333}}
.thumb{{width:128px;max-width:128px;height:auto}} td{{vertical-align:top}}
a{{color:#7cf}}</style>
<div id=map></div>
<div class=wrap>
<p class=big>MASt3R-SfM · {stats['n']} images · {stats['pairs']} pairs ·
recon {stats['recon_s']:.0f}s · <span class=k>median camera↔GPS residual {stats['med_resid']:.1f} m</span>
(mean {stats['mean_resid']:.1f}, max {stats['max_resid']:.1f}); scale {stats['scale']:.3g} units/m</p>
{f'<p style="color:#fa8">⊘ correspondence-masking: {stats.get("n_masked",0)} frame(s) masked, dropped <b>{stats.get("corr_dropped",0)}/{stats.get("corr_total",0)}</b> correspondences in masked regions (red in the mask column = pixels excluded from matching, not painted).</p>' if stats.get('n_masked') else ''}
<p>Blue track = GPS. Orange track = MASt3R-recovered camera centres, Umeyama-aligned
(similarity: scale+rotation+translation) onto GPS. Tight overlap ⇒ the reconstruction
is globally self-consistent <i>and</i> agrees with independent GPS — the honest success signal.</p>
<div>
  <img src="{td_png}" title="top-down point cloud (red = cameras)">
  <a href="points.ply">points.ply</a> · <a href="scene.npz">scene.npz</a> ·
  {stats['npts']} sparse points
</div>
{pmat_html}
<table><tr><th>#</th><th>photo (input to MASt3R)</th>{'<th>mask (red=dropped)</th>' if has_mask else ''}{'<th>depth (near=red)</th>' if has_depth else ''}{'<th>conf (violet→yellow)</th>' if has_conf else ''}<th>id</th><th>captured</th><th>compass</th><th>resid</th><th>title</th></tr>
{rows}</table>
</div>
<script>
var map=L.map('map').setView([{lat0},{lon0}],17);
L.tileLayer('https://tiles4.ueueeu.eu/tile/{{z}}/{{x}}/{{y}}.png',{{maxZoom:23,maxNativeZoom:20,
 attribution:'&copy; OpenStreetMap contributors · tiles4.ueueeu.eu'}}).addTo(map);
var gps={gps_js}, rec={rec_js}, ids={ids}, resid={resid_js};
L.polyline(gps,{{color:'#39f',weight:2}}).addTo(map);
L.polyline(rec,{{color:'#f80',weight:2,dashArray:'4 4'}}).addTo(map);
gps.forEach(function(p,i){{
  L.circleMarker(p,{{radius:4,color:'#39f',fillOpacity:.9}}).bindTooltip('GPS '+ids[i]).addTo(map);
}});
rec.forEach(function(p,i){{
  L.circleMarker(p,{{radius:4,color:'#f80',fillOpacity:.9}}).bindTooltip('rec '+ids[i]+' ('+resid[i]+'m)').addTo(map);
  L.polyline([gps[i],p],{{color:'#666',weight:1}}).addTo(map);
}});
var all=gps.concat(rec); map.fitBounds(all,{{padding:[40,40]}});
</script>"""
    with open(os.path.join(out, "report.html"), "w") as f:
        f.write(html)


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--center", default="50.1172,14.4893")
    ap.add_argument("--radius", type=float, default=300)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--win", type=int, default=3, help="sliding-window half-size for pairs")
    ap.add_argument("--pairs", default="swin", choices=["swin", "complete", "bearing"],
                    help="pairing strategy: time-window / exhaustive / spatial+bearing-overlap")
    ap.add_argument("--pair_dist", type=float, default=80, help="bearing mode: max pair distance (m)")
    ap.add_argument("--pair_dang", type=float, default=110, help="bearing mode: max bearing diff (deg)")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--niter1", type=int, default=300)
    ap.add_argument("--niter2", type=int, default=300)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--maxscan", type=int, default=0)
    ap.add_argument("--stride", type=int, default=1, help="subsample step in capture order")
    ap.add_argument("--after", default="", help="keep captures >= this (YYYY-MM-DD HH:MM:SS)")
    ap.add_argument("--before", default="", help="keep captures <= this (YYYY-MM-DD HH:MM:SS)")
    ap.add_argument("--inject", default="", help="comma-sep photo id-prefixes to add as impostors")
    ap.add_argument("--dense", action="store_true", help="also extract+save the DENSE point cloud")
    ap.add_argument("--min_conf", type=float, default=1.5, help="dense-point confidence threshold")
    ap.add_argument("--mask_anon", action="store_true",
                    help="correspondence-mask anonymization doodle boxes (drop matches inside them)")
    ap.add_argument("--mask_solocator", action="store_true",
                    help="gray out Solocator overlay (green marks + top bar) on Solocator-origin photos")
    ap.add_argument("--out", default=os.path.join(HERE, "runs", "recon"))
    ap.add_argument("--photos_csv", default="", help="explicit photos CSV (overrides /shared/dbdump glob)")
    a = ap.parse_args()
    global PHOTOS_CSV
    PHOTOS_CSV = a.photos_csv or None
    lat0, lon0 = map(float, a.center.split(","))
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()

    sub = select_cluster((lat0, lon0), a.radius, a.n, a.start, a.maxscan, a.stride, a.after, a.before)
    inj = fetch_by_ids([p.strip() for p in a.inject.split(",") if p.strip()], (lat0, lon0))
    if inj:
        log(f"injecting {len(inj)} impostor(s): {[p['id'][:8] for p in inj]}")
        sub = sub + inj
    if len(sub) < 2:
        raise SystemExit("need >=2 images")
    paths = download(sub, os.path.join(a.out, "imgs"),
                     mask_anon=a.mask_anon, mask_solocator=a.mask_solocator)

    log("loading MASt3R model (cpu)…")
    for p in (MAST3R_REPO, os.path.join(MAST3R_REPO, "dust3r"),
              os.path.join(MAST3R_REPO, "dust3r", "croco")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import torch
    from mast3r.model import AsymmetricMASt3R
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment
    from dust3r.image_pairs import make_pairs
    from dust3r.utils.image import load_images
    # NB: do NOT globally disable grad — sparse_scene_optimizer needs autograd for
    # its optimization loop. The MASt3R forward passes manage no_grad internally.
    model = AsymmetricMASt3R.from_pretrained(MAST3R_CKPT).to(a.device).eval()

    imgs = load_images(paths, size=a.size, verbose=True)
    if a.mask_solocator or a.mask_anon:
        # Correspondence-level masks, built in the EXACT loaded frame MASt3R matches on (same
        # coords as the cached xy correspondences). Keyed by PATH: convert_dust3r_pairs_naming
        # remaps each img's 'instance' to paths[idx], which is what the corres cache keys on.
        ng = na = 0
        for im in imgs:
            i = im["idx"]; p = sub[i]
            H2, W2 = int(im["true_shape"][0][0]), int(im["true_shape"][0][1])
            rgb = ((im["img"][0].permute(1, 2, 0).cpu().numpy() * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8)
            m = None
            if a.mask_solocator:                              # neon-green overlay marks
                gm = green_overlay_mask(rgb)
                if gm is not None:
                    m = gm.copy(); ng += 1
            if a.mask_anon and p.get("anon_saved"):           # anonymization doodle boxes
                W1, H1 = p["saved_wh"]
                am = np.zeros((H2, W2), bool); hit = False
                for box in p["anon_saved"]:
                    (bx1, by1, bx2, by2), _ = map_box_to_loaded(box, W1, H1, size=a.size)
                    if bx2 > bx1 and by2 > by1:
                        am[by1:by2, bx1:bx2] = True; hit = True
                if hit:
                    m = am if m is None else (m | am); na += 1
            if m is not None:
                CORR_MASKS[paths[i]] = m
                save_mask_overlay(rgb, m, os.path.join(a.out, f"mask_{i:03d}_{p['id'][:8]}.png"))
        if CORR_MASKS:
            install_corr_masking()
            log(f"correspondence-masking: green overlay on {ng}, anon boxes on {na} frame(s)")
    if a.pairs == "complete":
        pairs = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)
        log(f"pairing=complete -> {len(pairs)} directed pairs")
    elif a.pairs == "bearing":
        # pair by VIEW OVERLAP not time: spatially near AND within a generous bearing window.
        # (compass is noisy as a measurement but fine as a pairing heuristic; frames with no
        #  bearing are kept as candidates so we never miss a real overlap.)
        allp = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)
        def keep(a_, b_):
            i, j = a_["idx"], b_["idx"]
            d = math.hypot(sub[i]["e"] - sub[j]["e"], sub[i]["n"] - sub[j]["n"])
            if d > a.pair_dist:
                return False
            bi, bj = sub[i]["brg"], sub[j]["brg"]
            if bi is not None and bj is not None:
                if abs((bi - bj + 180) % 360 - 180) > a.pair_dang:
                    return False
            return True
        pairs = [(x, y) for (x, y) in allp if keep(x, y)]
        log(f"pairing=bearing (dist<{a.pair_dist}m, |dbrg|<{a.pair_dang}°) -> "
            f"{len(pairs)}/{len(allp)} directed pairs kept")
    else:
        win = min(a.win, len(imgs) - 1)
        sg = f"swin-{win}-noncyclic"
        pairs = make_pairs(imgs, scene_graph=sg, prefilter=None, symmetrize=True)
        log(f"pairing={sg} -> {len(pairs)} directed pairs")
    if not pairs:
        raise SystemExit("no pairs survived the pairing filter — loosen --pair_dist/--pair_dang")
    log("running sparse_global_alignment…")
    tr = time.time()
    cache = os.path.join(a.out, "cache")
    scene = sparse_global_alignment(
        paths, pairs, cache, model,
        lr1=0.07, niter1=a.niter1, lr2=0.01, niter2=a.niter2,
        device=a.device, matching_conf_thr=5.0, shared_intrinsics=False)
    recon_s = time.time() - tr
    log(f"reconstruction done in {recon_s:.0f}s")

    # extract
    poses = scene.get_im_poses().detach().cpu().numpy()        # N x 4x4 cam2world
    focals = scene.get_focals().detach().cpu().numpy().ravel()
    pts_l = scene.get_sparse_pts3d()
    cols_l = scene.get_pts3d_colors()
    def cat(x):
        import numpy as _np, torch as _t
        if isinstance(x, (list, tuple)):
            x = [xx.detach().cpu().numpy() if hasattr(xx, "detach") else _np.asarray(xx) for xx in x]
            x = [xx.reshape(-1, 3) for xx in x]
            return _np.concatenate(x, 0) if x else _np.zeros((0, 3))
        return x.detach().cpu().numpy().reshape(-1, 3) if hasattr(x, "detach") else _np.asarray(x).reshape(-1, 3)
    pts = cat(pts_l); cols = cat(cols_l)
    cams = poses[:, :3, 3]                                       # camera centers
    log(f"{len(pts)} sparse points, {len(cams)} cameras, focals={np.round(focals,1)}")

    np.savez(os.path.join(a.out, "scene.npz"),
             poses=poses, focals=focals, points=pts, colors=cols, cams=cams)
    write_ply(os.path.join(a.out, "points.ply"), pts, cols)

    # DENSE extraction (one 3D point per confident pixel, colored from the RGB frames)
    dpts = dcols = None
    if a.dense:
        log("extracting dense point cloud (get_dense_pts3d)…")
        td0 = time.time()
        d_pts3d, d_depths, d_confs = scene.get_dense_pts3d(clean_depth=True)
        rgb = scene.imgs                                          # list of (H,W,3) in [0,1]
        def tn(x): return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)
        d_pts3d = [tn(p).reshape(-1, 3) for p in d_pts3d]
        d_confs = [tn(c).ravel() for c in d_confs]
        d_depths = [tn(dd) for dd in d_depths]
        # per-frame depth (near=red/far=blue) + confidence (violet=low/yellow=high) renders
        for i, dd in enumerate(d_depths):
            H, W = np.asarray(rgb[i]).shape[:2]
            dm = dd.reshape(H, W) if dd.size == H * W else np.asarray(dd)
            render_depth(dm, os.path.join(a.out, f"depth_{i:03d}_{sub[i]['id'][:8]}.png"))
            cc = d_confs[i].reshape(H, W) if d_confs[i].size == H * W else d_confs[i]
            render_conf(cc, os.path.join(a.out, f"conf_{i:03d}_{sub[i]['id'][:8]}.png"))
        msk = [c > a.min_conf for c in d_confs]
        dpts = np.concatenate([p[m] for p, m in zip(d_pts3d, msk)]) if d_pts3d else np.zeros((0, 3))
        dcols = np.concatenate([np.asarray(r).reshape(-1, 3)[m] for r, m in zip(rgb, msk)])
        log(f"dense: {len(dpts)} points (conf>{a.min_conf}) in {time.time()-td0:.0f}s")
        # full arrays for later review (compressed)
        np.savez_compressed(os.path.join(a.out, "dense.npz"),
                            points=dpts, colors=dcols,
                            depthmaps=np.array(d_depths, dtype=object),
                            poses=poses, focals=focals)
        # cap ascii ply at ~2M pts so it stays openable; keep full set in dense.npz
        if len(dpts) > 2_000_000:
            sel = np.linspace(0, len(dpts) - 1, 2_000_000).astype(int)
            write_ply(os.path.join(a.out, "dense.ply"), dpts[sel], dcols[sel])
        else:
            write_ply(os.path.join(a.out, "dense.ply"), dpts, dcols)

    td = os.path.join(a.out, "topdown.png")
    try:
        topdown_png(td, dpts if dpts is not None else pts,
                    dcols if dcols is not None else cols, cams)
    except Exception as e:
        log("topdown render failed:", e); td = None

    # align recovered cams -> GPS-ENU (3D: east, north, altitude)
    kx = 111320.0 * math.cos(math.radians(lat0)); ky = 110540.0
    alt0 = np.mean([p["alt"] for p in sub if p["alt"] is not None]) if any(p["alt"] is not None for p in sub) else 0.0
    gps_enu = np.array([[p["e"], p["n"], (p["alt"] - alt0) if p["alt"] is not None else 0.0] for p in sub])
    # Fit the similarity on the REAL cluster only; impostors must not influence the alignment.
    real = np.array([not p.get("inj") for p in sub])
    s, R, t = umeyama(cams[real], gps_enu[real])
    rec_enu = (s * (R @ cams.T)).T + t
    resid = np.linalg.norm(rec_enu[:, :2] - gps_enu[:, :2], axis=1)   # horizontal residual
    cam_ll_gps = [(p["lat"], p["lon"]) for p in sub]
    cam_ll_rec = [enu_to_ll(rec_enu[i, 0], rec_enu[i, 1], lat0, lon0) for i in range(len(sub))]

    rr = resid[real]
    inj_resid = {p["id"][:8]: float(resid[i]) for i, p in enumerate(sub) if p.get("inj")}
    if inj_resid:
        log(f"IMPOSTOR residuals (vs own GPS, alignment fit on real frames only): {inj_resid}")
        log(f"  real frames: median {np.median(rr):.1f}m  ·  impostor(s) should be FAR larger")

    # correspondence-count connectivity (post-masking) → matrix image + summary
    pair_stats = {}
    try:
        mat = pair_count_matrix(cache, paths)
        render_pair_matrix(mat, os.path.join(a.out, "pairs_matrix.png"))
        sym = mat + mat.T
        deg = (sym > 0).sum(1)                       # how many frames each frame connects to
        nz = sym[np.triu_indices(len(paths), 1)]
        nz = nz[nz > 0]
        pair_stats = dict(connected_pairs=int(len(nz)),
                          median_matches=int(np.median(nz)) if len(nz) else 0,
                          min_matches=int(nz.min()) if len(nz) else 0,
                          isolated=[sub[i]["id"][:8] for i in range(len(paths)) if deg[i] == 0])
        log(f"connectivity: {pair_stats['connected_pairs']} connected pairs, "
            f"median {pair_stats['median_matches']} matches, isolated {pair_stats['isolated']}")
    except Exception as e:
        log("pair matrix failed:", e)

    stats = dict(n=len(sub), n_real=int(real.sum()), pairs=len(pairs), recon_s=recon_s, npts=len(pts),
                 ndense=(int(len(dpts)) if dpts is not None else 0),
                 scale=float(s), med_resid=float(np.median(rr)),
                 mean_resid=float(rr.mean()), max_resid=float(rr.max()),
                 corr_dropped=CORR_STATS["dropped"], corr_total=CORR_STATS["total"],
                 n_masked=len(CORR_MASKS), pair_stats=pair_stats, impostor_resid=inj_resid, topdown=td)
    report_html(a.out, sub, (lat0, lon0), cam_ll_gps, cam_ll_rec, resid, stats)

    # comprehensive metadata for later review: every input + every recovered quantity
    meta = {
        "args": vars(a), "center": [lat0, lon0],
        "alignment": {"scale_units_per_m": float(s), "R": R.tolist(), "t": t.tolist(),
                      "alt0": float(alt0)},
        "stats": stats,
        "frames": [{
            "idx": i, "id": p["id"], "injected": bool(p.get("inj")),
            "gps": [p["lat"], p["lon"]], "altitude": p["alt"],
            "compass_angle": p["brg"], "captured_at": p["cap"], "title": p["ttl"],
            "dist_to_center_m": round(p["d"], 1), "source_url": p["full"],
            "focal_px": float(focals[i]),
            "pose_cam2world": poses[i].tolist(),
            "recovered_gps": list(cam_ll_rec[i]),
            "residual_m": float(resid[i]),
        } for i, p in enumerate(sub)],
    }
    json.dump(meta, open(os.path.join(a.out, "metadata.json"), "w"), indent=2)
    json.dump({**stats, "ids": [p["id"] for p in sub]},
              open(os.path.join(a.out, "stats.json"), "w"), indent=2)
    log(f"DONE total {time.time()-t0:.0f}s · median residual {stats['med_resid']:.1f}m · "
        f"report: {os.path.join(a.out,'report.html')}")


if __name__ == "__main__":
    main()
