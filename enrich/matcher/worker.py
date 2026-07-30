"""MASt3R pair-match worker — the workbench's first queue worker.

Untrusted-worker topology (cf. accounts-assessor): consumes `match_pair` jobs from
RabbitMQ, computes with the LOCAL scripts/enrich stack (venv w/ torch + MASt3R repo +
checkpoint), and POSTs results (+ overlay JPEG) back to the API with a token. No DB
credentials — the same shape a rented GPU box will use, pointed at a tunneled broker.

Run (from repo root, using the existing enrich experiments venv):
    scripts/enrich/.venv/bin/python -m remoulade enrich.matcher.worker --processes 1 --threads 1
or:  cd enrich/matcher && ../../scripts/enrich/.venv/bin/python -m remoulade worker --processes 1 --threads 1
"""
import io
import json
import math
import os
import socket
import sys
import urllib.request

import remoulade
from remoulade.brokers.rabbitmq import RabbitmqBroker

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ENRICH_SCRIPTS = os.path.join(REPO, "scripts", "enrich")
MAST3R_REPO = os.getenv("MAST3R_REPO", os.path.join(ENRICH_SCRIPTS, "mast3r_repo"))
MAST3R_CKPT = os.getenv("MAST3R_CKPT", os.path.join(MAST3R_REPO, "checkpoints", "mast3r.pth"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "enrich:enrich@127.0.0.1:5672")
MAXKP = 1536
MARGIN = 0.10
MAXDIM = 2048   # cap crop long side; MASt3R works at 512 so full-res is wasted

broker = RabbitmqBroker(url=f"amqp://{RABBITMQ_URL}?timeout=15", confirm_delivery=True)
remoulade.set_broker(broker)

# --- OOM protection -----------------------------------------------------------
# RAM gate (pattern: backend/worker/throttle.py → pics src/lib/throttle.py): wait
# until enough RAM is actually available before the heavy phase; unlike the
# wait-forever pipeline variant, a queue job times out and FAILS VISIBLY (the
# error travels back via the callback). Belt half; braces = the systemd
# MemoryMax scope in run_worker.sh, so a runaway allocation kills only the
# worker unit, never the box.
MATCHER_REQUIRED_GB = float(os.getenv("MATCHER_REQUIRED_GB", "6"))
RAM_GATE_TIMEOUT_S = float(os.getenv("MATCHER_RAM_GATE_TIMEOUT_S", "600"))


def ram_gate(required_gb: float = MATCHER_REQUIRED_GB,
             timeout_s: float = RAM_GATE_TIMEOUT_S) -> None:
    import time

    import psutil
    t0 = time.monotonic()
    while True:
        avail_gb = psutil.virtual_memory().available / 2**30
        if avail_gb >= required_gb:
            return
        if time.monotonic() - t0 > timeout_s:
            raise MemoryError(
                f"RAM gate: only {avail_gb:.1f} GiB available "
                f"(< {required_gb} GiB required) for {timeout_s:.0f}s")
        print(f"ram_gate: {avail_gb:.1f} < {required_gb} GiB, waiting…", flush=True)
        time.sleep(5)


_model = None


def _load_model():
    global _model
    if _model is None:
        for p in (MAST3R_REPO, os.path.join(MAST3R_REPO, "dust3r"),
                  os.path.join(MAST3R_REPO, "dust3r", "croco")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from mast3r.model import AsymmetricMASt3R
        print("loading MASt3R…", flush=True)
        _model = AsymmetricMASt3R.from_pretrained(MAST3R_CKPT).eval()
    return _model


def _fetch(url, timeout=90):
    from PIL import Image
    req = urllib.request.Request(url, headers={"User-Agent": "hillview-matcher/0.1"})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=timeout).read())).convert("RGB")


def _dzi_region(pyr, nx0, ny0, nx1, ny1, max_px=MAXDIM):
    """Crop from DZI pyramid tiles (ported from scripts/enrich/viz_app.py).

    Picks the pyramid level so the crop's long side lands ≤ max_px — a wide
    target window would otherwise pull hundreds of full-res tiles into a
    multi-GB canvas only to be shrunk to 512 by MASt3R anyway.
    Returns (image, (nx0, ny0, nx1, ny1)) — the bounds actually delivered,
    normalized to the source photo (clamping can shrink the request).
    """
    from PIL import Image
    base, fmt = pyr["tiles_url"].rstrip("/"), pyr.get("format", "webp")
    TS, OV = int(pyr["tile_size"]), int(pyr["overlap"])
    W, H = int(pyr["width"]), int(pyr["height"])
    maxlevel = math.ceil(math.log2(max(W, H)))
    nx0, nx1 = sorted((max(0.0, nx0), min(1.0, nx1)))
    ny0, ny1 = sorted((max(0.0, ny0), min(1.0, ny1)))
    ds = 1
    while max((nx1 - nx0) * W, (ny1 - ny0) * H) / ds > max_px and ds < 1 << maxlevel:
        ds *= 2
    level = maxlevel - int(math.log2(ds))
    Wl, Hl = math.ceil(W / ds), math.ceil(H / ds)
    px0, px1 = sorted((max(0, int(nx0 * Wl)), min(Wl, int(nx1 * Wl))))
    py0, py1 = sorted((max(0, int(ny0 * Hl)), min(Hl, int(ny1 * Hl))))
    c0, c1, r0, r1 = px0 // TS, (px1 - 1) // TS, py0 // TS, (py1 - 1) // TS
    ox, oy = c0 * TS, r0 * TS
    canvas = Image.new("RGB", ((c1 - c0 + 1) * TS + OV + 1, (r1 - r0 + 1) * TS + OV + 1))
    for c in range(c0, c1 + 1):
        for r in range(r0, r1 + 1):
            try:
                tile = _fetch(f"{base}/{level}/{c}_{r}.{fmt}", timeout=60)
            except Exception:
                continue
            canvas.paste(tile, (c * TS - (OV if c > 0 else 0) - ox,
                                r * TS - (OV if r > 0 else 0) - oy))
    img = canvas.crop((px0 - ox, py0 - oy, px1 - ox, py1 - oy))
    return img, (px0 / Wl, py0 / Hl, px1 / Wl, py1 / Hl)


MAX_ASPECT = 2.0   # pano rects are extreme strips (20:1+); MASt3R's 512px
                   # resize would leave ~16px of height — no structure to match
                   # or fit a homography on. Grow the short side with context.


def _expand_aspect(rect, W, H, max_aspect=MAX_ASPECT):
    """Expand the short side of rect (normalized, on a W×H-px photo) about its
    center until the PIXEL aspect ratio is ≤ max_aspect."""
    x0, y0, x1, y1 = rect
    pw, ph = (x1 - x0) * W, (y1 - y0) * H
    if ph > 0 and pw / ph > max_aspect:
        half = pw / max_aspect / H / 2
        cy = (y0 + y1) / 2
        y0, y1 = cy - half, cy + half
    elif pw > 0 and ph / pw > max_aspect:
        half = ph / max_aspect / W / 2
        cx = (x0 + x1) / 2
        x0, x1 = cx - half, cx + half
    return x0, y0, x1, y1


def _get_crop(crop_spec):
    """→ (image, bounds) with bounds = delivered crop in source-normalized coords.

    context_rect (optional) decouples the CROPPED region from the annotation
    rect: a small rect matched against a wide target window fails on scale
    mismatch (the object fills the crop but ~4% of the window), so the caller
    supplies a context region of comparable angular span; `rect` stays the
    annotation rect and is what _project_rect projects."""
    ctx = crop_spec.get("context_rect")
    if ctx:
        cx, cy, cw, ch = ctx
        rect = (cx, cy, cx + cw, cy + ch)
    else:
        x, y, w, h = crop_spec["rect"]
        m = float(crop_spec.get("margin", MARGIN))
        rect = (x - m * w, y - m * h, x + w + m * w, y + h + m * h)
    if crop_spec.get("pyramid"):
        pyr = crop_spec["pyramid"]
        rect = _expand_aspect(rect, int(pyr["width"]), int(pyr["height"]))
        return _dzi_region(pyr, *rect,
                           max_px=int(crop_spec.get("max_px", MAXDIM)))
    img = _fetch(crop_spec["full_url"])
    W, H = img.size
    rect = _expand_aspect(rect, W, H)
    px0, py0 = max(0, int(rect[0] * W)), max(0, int(rect[1] * H))
    px1, py1 = min(W, int(rect[2] * W)), min(H, int(rect[3] * H))
    return img.crop((px0, py0, px1, py1)), (px0 / W, py0 / H, px1 / W, py1 / H)


def _mast3r_match(crop, photo):
    """→ (raw, inliers, xy1, xy2, mask, images) — the viz_app _mast3r + RANSAC path.
    xy1/xy2 are correspondence coords in the two LOADED (512-resized) images."""
    import tempfile

    import cv2
    import numpy as np
    import torch
    model = _load_model()
    from dust3r.inference import inference
    from dust3r.utils.image import load_images
    from mast3r.fast_nn import fast_reciprocal_NNs

    with tempfile.TemporaryDirectory() as td:
        p0, p1 = os.path.join(td, "a.jpg"), os.path.join(td, "b.jpg")
        crop.save(p0, "JPEG", quality=92)
        photo.save(p1, "JPEG", quality=92)
        images = load_images([p0, p1], size=512, verbose=False)
    with torch.inference_mode():
        out = inference([tuple(images)], model, "cpu", batch_size=1, verbose=False)
    v1, v2 = out["pred1"], out["pred2"]
    d1, d2 = v1["desc"][0], v2["desc"][0]
    m0 = fast_reciprocal_NNs(d1, d2, subsample_or_initxy1=8,
                             device="cpu", dist="dot", block_size=2**13)
    xy1, xy2 = m0
    raw = len(xy1)
    inliers, mask = 0, None
    if raw >= 8:
        F, mask = cv2.findFundamentalMat(
            np.float32(xy1), np.float32(xy2), cv2.FM_RANSAC, 3.0, 0.99)
        inliers = int(mask.sum()) if mask is not None else 0
    return raw, inliers, xy1, xy2, mask, images


def _load_geom(w, h, size=512):
    """Replicate dust3r load_images(size=512): resize long side → size, then
    center-crop both dims to multiples of 16. Returns (sx, sy, offx, offy)
    mapping ORIGINAL px → LOADED px:  loaded = orig*s − off."""
    S = max(w, h)
    nw, nh = round(w * size / S), round(h * size / S)
    cx, cy = nw // 2, nh // 2
    halfw, halfh = (cx // 8) * 8, (cy // 8) * 8
    if nw == nh:
        halfh = 3 * halfw // 4   # dust3r crops square inputs to 4:3
    return nw / w, nh / h, cx - halfw, cy - halfh


def _rect_loaded_pts(rect, crop, crop_bounds):
    """Donor rect corners in the LOADED (512-resized) crop's pixel coords."""
    x, y, w, h = rect
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    cw, ch = crop.size
    bx0, by0, bx1, by1 = crop_bounds
    sx, sy, offx, offy = _load_geom(cw, ch)
    return [((cx - bx0) / (bx1 - bx0) * cw * sx - offx,
             (cy - by0) / (by1 - by0) * ch * sy - offy) for cx, cy in corners]


def _project_rect(rect, crop, crop_bounds, tgt, tgt_bounds, xy1, xy2):
    """Fit a transform on the correspondences and push the donor RECT through it.
    → {method, h_inliers, quad, bbox, pts_loaded} with quad/bbox normalized to
    the FULL target photo (via tgt_bounds), or None when no stable fit."""
    import cv2
    import numpy as np
    if len(xy1) < 8:
        return None
    Hm, hmask = cv2.findHomography(np.float32(xy1), np.float32(xy2),
                                   cv2.RANSAC, 3.0)
    method = "homography"
    if Hm is None or hmask is None or int(hmask.sum()) < 8:
        A, amask = cv2.estimateAffinePartial2D(
            np.float32(xy1), np.float32(xy2),
            method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if A is None or amask is None or int(amask.sum()) < 6:
            return None
        Hm, hmask, method = np.vstack([A, [0.0, 0.0, 1.0]]), amask, "affine"

    pts = _rect_loaded_pts(rect, crop, crop_bounds)
    pts = cv2.perspectiveTransform(np.float32([pts]), np.float64(Hm))[0]

    tw, th = tgt.size
    tbx0, tby0, tbx1, tby1 = tgt_bounds
    tsx, tsy, toffx, toffy = _load_geom(tw, th)
    quad = [(float(tbx0 + (px + toffx) / tsx / tw * (tbx1 - tbx0)),
             float(tby0 + (py + toffy) / tsy / th * (tby1 - tby0)))
            for px, py in pts]
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    return {"method": method, "h_inliers": int(hmask.sum()),
            "quad": [[round(a, 6), round(b, 6)] for a, b in quad],
            "bbox": {"x": round(min(xs), 6), "y": round(min(ys), 6),
                     "w": round(max(xs) - min(xs), 6),
                     "h": round(max(ys) - min(ys), 6)},
            "pts_loaded": [[float(a), float(b)] for a, b in pts]}


OVERLAY_SCALE = 2       # loaded images are ≤512px — upscale for legibility
OVERLAY_LINES = 120     # sampled inlier lines; density reads as noise


def _overlay_jpeg(images, xy1, xy2, mask, proj_pts=None, src_pts=None):
    """Side-by-side overlay. Inlier lines are RAINBOW-COLORED BY DONOR-X: a
    geometrically consistent match shows as a smooth left→right hue sweep, and
    any crossing outlier breaks the gradient visibly (a same-colored dense
    bundle just reads as noise). Amber = donor rect (left), cyan = its
    projection (right); sparse red = outliers."""
    import cv2
    import numpy as np
    raw = len(xy1)
    S = OVERLAY_SCALE
    a1 = np.asarray(images[0]["img"][0].permute(1, 2, 0) * 0.5 + 0.5) * 255
    a2 = np.asarray(images[1]["img"][0].permute(1, 2, 0) * 0.5 + 0.5) * 255
    a1 = cv2.resize(a1.astype("uint8"), None, fx=S, fy=S,
                    interpolation=cv2.INTER_LINEAR)
    a2 = cv2.resize(a2.astype("uint8"), None, fx=S, fy=S,
                    interpolation=cv2.INTER_LINEAR)
    h = max(a1.shape[0], a2.shape[0])
    canvas = np.zeros((h, a1.shape[1] + a2.shape[1], 3), "uint8")
    canvas[:a1.shape[0], :a1.shape[1]] = a1
    canvas[:a2.shape[0], a1.shape[1]:] = a2
    bgr = cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
    off = a1.shape[1]
    w1 = max(a1.shape[1], 1)

    def hue_color(x_px):
        hue = int(max(0.0, min(1.0, x_px * S / w1)) * 150)   # red→cyan sweep
        px = np.uint8([[[hue, 200, 255]]])
        b, g, r = cv2.cvtColor(px, cv2.COLOR_HSV2BGR)[0, 0]
        return int(b), int(g), int(r)

    inliers = [i for i in range(raw) if mask is not None and bool(mask[i])]
    outliers = [i for i in range(raw) if mask is None or not bool(mask[i])]
    step = max(1, len(inliers) // OVERLAY_LINES)
    for i in inliers[::step]:
        cv2.line(bgr, (int(xy1[i][0] * S), int(xy1[i][1] * S)),
                 (int(xy2[i][0] * S) + off, int(xy2[i][1] * S)),
                 hue_color(xy1[i][0]), 1, cv2.LINE_AA)
    if len(outliers) <= 60:   # only when sparse — that's when they're news
        for i in outliers:
            cv2.line(bgr, (int(xy1[i][0] * S), int(xy1[i][1] * S)),
                     (int(xy2[i][0] * S) + off, int(xy2[i][1] * S)),
                     (50, 50, 210), 1, cv2.LINE_AA)
    if src_pts:
        poly = np.int32([[int(px * S), int(py * S)] for px, py in src_pts])
        cv2.polylines(bgr, [poly], isClosed=True, color=(58, 162, 224), thickness=2)
    if proj_pts:
        poly = np.int32([[int(px * S) + off, int(py * S)] for px, py in proj_pts])
        cv2.polylines(bgr, [poly], isClosed=True, color=(230, 200, 0), thickness=2)
    okj, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return jpg.tobytes() if okj else None


@remoulade.actor(queue_name="matching", time_limit=30 * 60 * 1000, max_retries=1)
def match_pair(payload: dict) -> None:
    import requests
    rid = payload["result_id"]
    print(f"match_pair {rid}…", flush=True)
    result = {"result_id": rid, "worker": socket.gethostname(), "status": "done"}
    overlay = None
    try:
        ram_gate()   # before the heavy phase (model load + inference)
        crop, crop_bounds = _get_crop(payload["crop"])
        tgt_spec = payload.get("photo")
        if isinstance(tgt_spec, dict):
            # target is a WINDOW of a (usually huge) photo, cropped from its
            # pyramid — the pano→pano annotation-transfer path
            photo, tgt_bounds = _get_crop(tgt_spec)
        else:
            photo, tgt_bounds = _fetch(payload["photo_url"]), (0.0, 0.0, 1.0, 1.0)
        raw, inliers, xy1, xy2, mask, images = _mast3r_match(crop, photo)
        proj = _project_rect(payload["crop"]["rect"], crop, crop_bounds,
                             photo, tgt_bounds, xy1, xy2)
        try:
            src_pts = _rect_loaded_pts(payload["crop"]["rect"], crop, crop_bounds)
        except (KeyError, ZeroDivisionError):
            src_pts = None
        overlay = _overlay_jpeg(images, xy1, xy2, mask,
                                proj["pts_loaded"] if proj else None, src_pts)
        result.update({"raw": raw, "inliers": inliers,
                       "ratio": round(inliers / raw, 3) if raw else 0.0})
        if proj:
            result["projection"] = {k: v for k, v in proj.items()
                                    if k != "pts_loaded"}
        print(f"  {rid}: raw={raw} inliers={inliers} "
              f"proj={proj['method'] if proj else None}", flush=True)
    except Exception as e:
        result.update({"status": "error", "error": f"{type(e).__name__}: {e}"})
        print(f"  {rid} FAILED: {e}", flush=True)
    files = {"overlay": ("overlay.jpg", overlay, "image/jpeg")} if overlay else None
    requests.post(payload["callback"],
                  data={"result_json": json.dumps(result)},
                  files=files,
                  headers={"X-Worker-Token": payload["token"]},
                  timeout=60)


remoulade.declare_actors([match_pair])
