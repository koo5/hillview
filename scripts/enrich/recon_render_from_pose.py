#!/usr/bin/env python3
"""Render a run's cloud through one of its own cameras, beside that camera's photograph.

The sharpest visual test of a solve there is: if the pose and the depth are right, the
render lands on the photo pixel for pixel; anything that drifted shows as a shift or as
the colour fringing of two surfaces slightly apart. Needs only the API.

Usage:  recon_render_from_pose.py <run_id> <idx[,idx...]> <out_dir> [--api URL]
"""
import argparse
import io
import os
import subprocess

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("idxs")
    ap.add_argument("out_dir")
    ap.add_argument("--api", default="http://127.0.0.1:8070/api/recon/runs")
    ap.add_argument("--max-points", type=int, default=1_500_000)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    import json
    cams = json.loads(subprocess.run(
        ["curl", "-s", f"{a.api}/{a.run_id}/cameras?enu=true&images=true&image_size=640"],
        capture_output=True, text=True).stdout)
    raw = subprocess.run(["curl", "-s", f"{a.api}/{a.run_id}/cloud.bin?enu=true&dense=true&max_points={a.max_points}"],
                         capture_output=True).stdout
    raw = np.frombuffer(raw, dtype=np.uint8)
    raw = raw[:len(raw) // 15 * 15].reshape(-1, 15)
    X = raw[:, :12].copy().view(np.float32).reshape(-1, 3).astype(np.float64)
    C = raw[:, 12:15]
    print(f"cloud {len(X)} points, {len(cams['frames'])} frames")
    for idx in [int(x) for x in a.idxs.split(",")]:
        f = next((x for x in cams["frames"] if x["idx"] == idx), None)
        if f is None:
            continue
        R, t, fp = np.array(f["rot"]), np.array(f["pos"]), f["focal_px"]
        w, h = f.get("img_w") or 384, f.get("img_h") or 512
        P = (X - t) @ R
        m = P[:, 2] > 0.05
        P, col = P[m], C[m]
        u = fp * P[:, 0] / P[:, 2] + w / 2
        v = fp * P[:, 1] / P[:, 2] + h / 2
        ok = (u >= 0) & (u < w) & (v >= 0) & (v < h)
        u, v, z, col = u[ok].astype(int), v[ok].astype(int), P[ok, 2], col[ok]
        o = np.argsort(-z)
        u, v, col = u[o], v[o], col[o]
        img = np.zeros((h, w, 3), np.uint8)
        for du in (0, 1):
            for dv in (0, 1):
                img[np.clip(v + dv, 0, h - 1), np.clip(u + du, 0, w - 1)] = col
        out = Image.new("RGB", (w * 2 + 8, h), (20, 20, 24))
        if f.get("image_url"):
            b = subprocess.run(["curl", "-s", f["image_url"]], capture_output=True).stdout
            try:
                out.paste(Image.open(io.BytesIO(b)).convert("RGB").resize((w, h)), (0, 0))
            except Exception:
                pass
        out.paste(Image.fromarray(img), (w + 8, 0))
        path = os.path.join(a.out_dir, f"{a.run_id[:8]}_{idx:03d}.png")
        out.save(path)
        print("wrote", path, int(ok.sum()), "pts on screen")


if __name__ == "__main__":
    main()
