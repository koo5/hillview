#!/usr/bin/env python3
"""Render-and-compare: does each frame's photograph agree with everyone else's geometry?

WHY. A run can be excellent on average and still contain frames that have quietly drifted.
On `dense-spotA-2026-08-19` the drift shows up in the model as a SECOND FLOOR -- a slab of
pavement 28 cm below the real one -- and it belongs to three specific frames. Reprojection
error flags them too, but only as a number; this says what is actually wrong, in pixels, in
the frame's own view.

METHOD. For frame i, fuse the dense points of every OTHER frame, render them through i's
solved pose and focal with a z-buffer, and find the 2-D shift that best matches i's real
photograph (normalised cross-correlation on the image gradient, so exposure differences do
not matter). A well-registered frame needs no shift. A drifted one needs a big one, and the
direction of the shift says which way it drifted.

Leaving the frame's own points OUT is the whole point: include them and every frame agrees
with itself perfectly, which is what makes reprojection error blind to this.

Usage:  python recon_frame_check.py <run_dir> [--json out.json]
Read-only; needs dense.npz and the run's imgs/, so it runs where the solve ran.
"""
import argparse
import glob
import json
import os
import sys

import numpy as np


def load_run(run_dir):
    z = np.load(os.path.join(run_dir, "dense.npz"), allow_pickle=True)
    md = json.load(open(os.path.join(run_dir, "metadata.json")))
    return z, md


def render(points, colors, R, t, focal, W, H, splat=2):
    """Painter's-algorithm render of a coloured point set through one camera."""
    P = (points - t) @ R                       # R is cam->world; R^T (x-t) == (x-t) @ R
    m = P[:, 2] > 0.05
    P, C = P[m], colors[m]
    u = focal * P[:, 0] / P[:, 2] + W / 2
    v = focal * P[:, 1] / P[:, 2] + H / 2
    ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u, v, z, C = u[ok].astype(np.int32), v[ok].astype(np.int32), P[ok, 2], C[ok]
    order = np.argsort(-z)
    u, v, C = u[order], v[order], C[order]
    img = np.zeros((H, W, 3), np.float32)
    hit = np.zeros((H, W), bool)
    for du in range(splat):
        for dv in range(splat):
            uu = np.clip(u + du, 0, W - 1)
            vv = np.clip(v + dv, 0, H - 1)
            img[vv, uu] = C
            hit[vv, uu] = True
    return img, hit


def grad(img):
    g = img.mean(2) if img.ndim == 3 else img
    gx = np.zeros_like(g); gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1, :] = g[2:, :] - g[:-2, :]
    return np.hypot(gx, gy)


def best_shift(a, b, mask, rad=24):
    """Shift (du, dv) maximising correlation of gradient images, and the peak value."""
    a = a * mask; b = b * mask
    a = a - a[mask].mean() if mask.any() else a
    b = b - b[mask].mean() if mask.any() else b
    a[~mask] = 0; b[~mask] = 0
    na = np.sqrt((a * a).sum()) or 1.0
    best = (-2.0, 0, 0)
    H, W = a.shape
    for dv in range(-rad, rad + 1, 2):
        for du in range(-rad, rad + 1, 2):
            bb = np.roll(np.roll(b, dv, 0), du, 1)
            nb = np.sqrt((bb * bb).sum()) or 1.0
            c = float((a * bb).sum() / (na * nb))
            if c > best[0]:
                best = (c, du, dv)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--json")
    ap.add_argument("--radius", type=int, default=24)
    ap.add_argument("--max-points", type=int, default=250_000,
                    help="per contributing frame, strided")
    a = ap.parse_args()
    z, md = load_run(a.run_dir)
    depth = z["depthmaps"].astype(np.float32)
    poses = z["poses"].astype(np.float64)
    focals = z["focals"].astype(np.float64)
    n = len(poses)
    imgs = sorted(glob.glob(os.path.join(a.run_dir, "imgs", "*.jpg")))
    if len(imgs) != n:
        print(f"warning: {len(imgs)} images for {n} frames", file=sys.stderr)

    from PIL import Image
    # imgs/ holds the ORIGINALS; the depthmaps -- and focal_px with them -- live in the
    # size the solver loaded, so derive that from the depth length and the aspect and
    # resize the photographs down to meet it.
    ow, oh = Image.open(imgs[0]).size
    npx = depth.shape[1]
    H = int(round((npx * oh / ow) ** 0.5))
    W = int(round(npx / H))
    if W * H != npx:
        raise SystemExit(f"cannot factor {npx} px at aspect {ow}x{oh} (got {W}x{H})")
    print(f"{n} frames, solver loaded {W}x{H} (originals {ow}x{oh})")

    vv, uu = np.mgrid[0:H, 0:W]
    uu = (uu - W / 2).ravel().astype(np.float64)
    vv = (vv - H / 2).ravel().astype(np.float64)
    photos = [np.asarray(Image.open(p).convert("RGB").resize((W, H)), np.float32) / 255.0
              for p in imgs]

    world, colour, owner = [], [], []
    for i in range(n):
        d = depth[i].reshape(-1).astype(np.float64)
        step = max(1, len(d) // a.max_points)
        P = np.stack([uu * d / focals[i], vv * d / focals[i], d], 1)[::step]
        world.append((poses[i][:3, :3] @ P.T).T + poses[i][:3, 3])
        colour.append(photos[i].reshape(-1, 3)[::step])
        owner.append(np.full(len(P), i, np.int16))
    world = np.concatenate(world); colour = np.concatenate(colour)
    owner = np.concatenate(owner)

    rows = []
    for i in range(n):
        keep = owner != i
        img, hit = render(world[keep], colour[keep],
                          poses[i][:3, :3], poses[i][:3, 3], focals[i], W, H)
        c, du, dv = best_shift(grad(photos[i]), grad(img), hit, a.radius)
        rows.append({"idx": i, "corr": round(c, 4), "du": du, "dv": dv,
                     "shift_px": round(float(np.hypot(du, dv)), 1),
                     "coverage": round(float(hit.mean()), 3)})
        print(f"  frame {i:3d}  corr {c:.3f}  shift ({du:+3d},{dv:+3d}) = "
              f"{np.hypot(du, dv):5.1f} px  coverage {hit.mean():.2f}", flush=True)

    sh = np.array([r["shift_px"] for r in rows])
    print(f"\nshift px: median {np.median(sh):.1f}  p90 {np.percentile(sh, 90):.1f}  max {sh.max():.1f}")
    bad = [r for r in rows if r["shift_px"] > max(4.0, 3 * np.median(sh))]
    print("frames needing a shift the rest do not:",
          ", ".join(f"{r['idx']}({r['shift_px']:.0f}px)" for r in bad) or "none")
    if a.json:
        json.dump({"frames": rows, "median_shift_px": float(np.median(sh)),
                   "outliers": [r["idx"] for r in bad]}, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
