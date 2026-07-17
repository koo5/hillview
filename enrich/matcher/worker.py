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


def _dzi_region(pyr, nx0, ny0, nx1, ny1):
    """Full-res crop from DZI pyramid tiles (ported from scripts/enrich/viz_app.py)."""
    from PIL import Image
    base, fmt = pyr["tiles_url"].rstrip("/"), pyr.get("format", "webp")
    TS, OV = int(pyr["tile_size"]), int(pyr["overlap"])
    W, H = int(pyr["width"]), int(pyr["height"])
    level = math.ceil(math.log2(max(W, H)))
    px0, px1 = sorted((max(0, int(nx0 * W)), min(W, int(nx1 * W))))
    py0, py1 = sorted((max(0, int(ny0 * H)), min(H, int(ny1 * H))))
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
    return canvas.crop((px0 - ox, py0 - oy, px1 - ox, py1 - oy))


def _get_crop(crop_spec):
    x, y, w, h = crop_spec["rect"]
    rect = (x - MARGIN * w, y - MARGIN * h, x + w + MARGIN * w, y + h + MARGIN * h)
    if crop_spec.get("pyramid"):
        return _dzi_region(crop_spec["pyramid"], *rect)
    img = _fetch(crop_spec["full_url"])
    W, H = img.size
    return img.crop((int(rect[0] * W), int(rect[1] * H),
                     int(rect[2] * W), int(rect[3] * H)))


def _mast3r_match(crop, photo):
    """→ (raw, inliers, overlay_jpeg_bytes) — the viz_app _mast3r + RANSAC path."""
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

    # overlay: side-by-side, green inlier lines
    a1 = np.asarray(images[0]["img"][0].permute(1, 2, 0) * 0.5 + 0.5) * 255
    a2 = np.asarray(images[1]["img"][0].permute(1, 2, 0) * 0.5 + 0.5) * 255
    a1, a2 = a1.astype("uint8"), a2.astype("uint8")
    h = max(a1.shape[0], a2.shape[0])
    canvas = np.zeros((h, a1.shape[1] + a2.shape[1], 3), "uint8")
    canvas[:a1.shape[0], :a1.shape[1]] = a1
    canvas[:a2.shape[0], a1.shape[1]:] = a2
    bgr = cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
    off = a1.shape[1]
    for i in range(raw):
        ok = mask is not None and bool(mask[i])
        color = (0, 210, 0) if ok else (60, 60, 200)
        if not ok and raw > 200:
            continue   # declutter: only draw outliers when sparse
        cv2.line(bgr, (int(xy1[i][0]), int(xy1[i][1])),
                 (int(xy2[i][0]) + off, int(xy2[i][1])), color, 1)
    okj, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return raw, inliers, (jpg.tobytes() if okj else None)


@remoulade.actor(queue_name="matching", time_limit=30 * 60 * 1000, max_retries=1)
def match_pair(payload: dict) -> None:
    import requests
    rid = payload["result_id"]
    print(f"match_pair {rid}…", flush=True)
    result = {"result_id": rid, "worker": socket.gethostname(), "status": "done"}
    overlay = None
    try:
        ram_gate()   # before the heavy phase (model load + inference)
        crop = _get_crop(payload["crop"])
        photo = _fetch(payload["photo_url"])
        raw, inliers, overlay = _mast3r_match(crop, photo)
        result.update({"raw": raw, "inliers": inliers,
                       "ratio": round(inliers / raw, 3) if raw else 0.0})
        print(f"  {rid}: raw={raw} inliers={inliers}", flush=True)
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
