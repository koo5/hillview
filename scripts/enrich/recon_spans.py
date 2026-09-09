#!/usr/bin/env python3
"""Fit a walk to GPS one span at a time, with the GPS allowed to be wrong.

WHY. A single similarity over a whole walk assumes the solve is one rigid thing. It is
not: where the chain breaks -- a staircase, an underpass, a swing of the camera -- the
solver continues with a fresh scale and a fresh heading, and one global fit then smears
the error of every span over every other. On newest-2026-09-08 that shows as a GPS
residual that climbs to 17 m, drops to 0.2 m at the join, and climbs to 18 m again.

And the GPS itself is not one rigid thing either. Under a bridge it is off, replaced by
rough manual overrides; coming out the other side it "wanders off across the street for
quite a few frames, before coming back to senses". A least-squares fit hands those frames
the same vote as the good ones.

So, per span (as delimited by the two-view chain report): pin gravity from the cameras,
then fit yaw + scale + translation to the HORIZONTAL GPS with an iteratively reweighted
fit -- frames whose GPS sits far from where the span's own shape puts them lose their
vote, and are named. The span's shape comes from the solve and is trusted; the GPS is
the thing on trial.

Usage:  recon_spans.py metadata.json --breaks 16,33 [--json out.json]
        (breaks = last frame index of each span but the final one)
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "enrich", "api", "app"))
import recon_ground as rg   # noqa: E402  the same gravity + constrained fit the API uses


def robust_fit(cams, gps, up, iters=6, k=2.5):
    """gravity_alignment, iterated with weights: a frame further than k x MAD from the
    fitted track is downweighted to zero on the next pass. Returns (s, R, t, weights)."""
    w = np.ones(len(cams))
    for _ in range(iters):
        keep = w > 0.5
        if keep.sum() < 3:
            break
        s, R, t = rg.gravity_alignment(cams[keep], gps[keep], up)
        fit = (s * (R @ cams.T)).T + t
        res = np.linalg.norm(fit[:, :2] - gps[:, :2], axis=1)
        mad = np.median(np.abs(res - np.median(res))) * 1.4826 or 1e-6
        thr = np.median(res) + k * mad
        w_new = (res <= max(thr, 2.0)).astype(float)   # never reject on sub-2 m noise
        if np.array_equal(w_new, w):
            break
        w = w_new
    return s, R, t, w, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata")
    ap.add_argument("--breaks", default="", help="comma list: last idx of each span")
    ap.add_argument("--json")
    a = ap.parse_args()
    md = json.load(open(a.metadata))
    frames = md["frames"]
    n = len(frames)
    poses = np.array([f["pose_cam2world"] for f in frames], dtype=float)
    cams, rots = poses[:, :3, 3], poses[:, :3, :3]
    lat0, lon0 = md["center"]
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110540.0
    gps = np.array([[(f["gps"][1] - lon0) * kx, (f["gps"][0] - lat0) * ky, 0.0] for f in frames])
    breaks = [int(x) for x in a.breaks.split(",") if x.strip()]
    edges = [0] + [b + 1 for b in breaks] + [n]
    spans = [(edges[i], edges[i + 1] - 1) for i in range(len(edges) - 1)]

    # gravity from the WHOLE run's cameras: roll is shared, and a short span alone may
    # not spread its headings enough to pin it
    ev = rg.estimate_up(np.zeros((0, 3)), cams, rots, float(md["alignment"]["scale_units_per_m"]))
    up = np.array(ev["up"] if ev["up"] else rg.estimate_up(np.zeros((0, 3)), cams, rots, 1.0)["up_phone"])
    print(f"{n} frames, {len(spans)} span(s), up from {ev['up_source']}")

    # the one-fit baseline, for comparison
    s0, R0, t0 = rg.gravity_alignment(cams, gps, up)
    fit0 = (s0 * (R0 @ cams.T)).T + t0
    res0 = np.linalg.norm(fit0[:, :2] - gps[:, :2], axis=1)
    print(f"  one fit over everything: GPS residual median {np.median(res0):.1f} m, p90 {np.percentile(res0, 90):.1f} m")

    out = []
    for si, (a0, a1) in enumerate(spans):
        idx = np.arange(a0, a1 + 1)
        if len(idx) < 3:
            print(f"  span {si}: frames {a0}-{a1}, too short to fit")
            continue
        s, R, t, w, res = robust_fit(cams[idx], gps[idx], up)
        rej = idx[w < 0.5]
        kept = res[w >= 0.5]
        print(f"  span {si}: frames {a0}-{a1} ({len(idx)})  scale {s:.3f} m/unit  "
              f"GPS residual on trusted frames median {np.median(kept):.1f} m p90 {np.percentile(kept, 90):.1f} m"
              + (f"   GPS DISTRUSTED on {len(rej)} frame(s): {rej.tolist()}" if len(rej) else ""))
        out.append({"span": si, "frames": [int(a0), int(a1)], "scale_units_per_m": float(s),
                    "R": R.tolist(), "t": t.tolist(),
                    "gps_distrusted": rej.tolist(),
                    "residual_m": {int(i): round(float(r), 2) for i, r in zip(idx, res)}})
    if a.json:
        json.dump({"up": up.tolist(), "up_source": ev["up_source"], "spans": out}, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
