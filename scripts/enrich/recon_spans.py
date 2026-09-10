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


def gps_prior_weights(frames):
    """How much to believe each frame's GPS before looking at the solve.

    Two rules, both read straight off the data (measured on newest-2026-09-08, 17:44-17:46):

    MANUAL BLOCK. A hand-placed location has no altitude, and the compass froze along
    with the GPS, so a run of frames with altitude absent and one repeated heading is a
    person placing waypoints. Rough, so a third of a vote -- and never a "trusted" frame.

    FIRST FIX AFTER. The first real fix after a manual block landed 66.9 m from the last
    waypoint. The receiver is re-acquiring; that frame gets no vote at all.
    """
    n = len(frames)
    alt = [f.get("altitude") for f in frames]
    hdg = [f.get("compass_angle") for f in frames]
    has_alt = sum(a is not None for a in alt)
    w = np.ones(n)
    tags = [""] * n
    if 0 < has_alt < n:                     # only meaningful where altitude is usually there
        manual = np.zeros(n, bool)
        for i in range(n):
            if alt[i] is not None:
                continue
            near = [hdg[j] for j in range(max(0, i - 2), min(n, i + 3)) if hdg[j] is not None]
            frozen = len(near) >= 3 and max(near) - min(near) < 0.5
            manual[i] = frozen
        for i in range(n):
            if manual[i]:
                w[i], tags[i] = 0.3, "manual"
            elif i > 0 and manual[i - 1]:
                w[i], tags[i] = 0.0, "first-fix-after-manual"
    return w, tags


def robust_fit(cams, gps, up, prior=None, iters=6, k=2.5):
    """gravity_alignment, iterated with weights: a frame further than k x MAD from the
    fitted track is downweighted to zero on the next pass. `prior` (0..1 per frame) caps
    the vote a frame can ever have. Returns (s, R, t, weights, residuals)."""
    prior = np.ones(len(cams)) if prior is None else np.asarray(prior, float)
    w = prior.copy()
    for _ in range(iters):
        keep = w > 0.2
        if keep.sum() < 3:
            break
        s, R, t = rg.gravity_alignment(cams[keep], gps[keep], up, weights=w[keep])
        fit = (s * (R @ cams.T)).T + t
        res = np.linalg.norm(fit[:, :2] - gps[:, :2], axis=1)
        mad = np.median(np.abs(res - np.median(res))) * 1.4826 or 1e-6
        thr = np.median(res) + k * mad
        w_new = (res <= max(thr, 2.0)).astype(float) * prior   # never reject on sub-2 m noise
        if np.array_equal(w_new, w):
            break
        w = w_new
    return s, R, t, w, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata")
    ap.add_argument("--breaks", default="", help="comma list: last idx of each span")
    ap.add_argument("--json")
    ap.add_argument("--run-dir", help="run dir with dense.npz: enables the eye-height scale")
    ap.add_argument("--eye", type=float, default=1.5, help="assumed phone height above the floor, m")
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

    # Per-frame camera height above its own floor, from the dense depthmaps. This is the
    # SCALE the GPS cannot give a span whose positions are hand-placed waypoints: under
    # the bridge the fit came back at 0.43 m per unit, a 2.6x error, because a block of
    # frames parked on one waypoint has no baseline at all. A phone is held ~1.5 m up.
    cam_h = {}
    if a.run_dir:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import recon_ground_split as gsp
        try:
            for r in gsp.analyse(a.run_dir, log=lambda *x: None).get("frames", []):
                if r.get("cam_height"):
                    cam_h[r["idx"]] = r["cam_height"]
        except Exception as e:
            print(f"  (no eye-height scale: {type(e).__name__}: {e})")

    out = []
    for si, (a0, a1) in enumerate(spans):
        idx = np.arange(a0, a1 + 1)
        if len(idx) < 3:
            print(f"  span {si}: frames {a0}-{a1}, too short to fit")
            continue
        pw, ptags = gps_prior_weights([frames[i] for i in idx])
        s, R, t, w, res = robust_fit(cams[idx], gps[idx], up, prior=pw)
        # eye-height scale: the span's own floor says what a solve unit is, and when the
        # GPS is rough (mostly manual) or the two disagree badly, the floor wins. The
        # solve's camera height here is in the run's ORIGINAL alignment units (metres of
        # the GPS-only fit), so the correction is relative to that fit's scale.
        hs = [cam_h[i] for i in idx if i in cam_h]
        scale_note = ""
        if hs:
            h_med = float(np.median(hs))
            s0 = float(md["alignment"]["scale_units_per_m"])
            s_eye = s0 * (a.eye / h_med)           # units->m that puts the camera at eye height
            manual_frac = sum(1 for tg in ptags if tg) / max(len(ptags), 1)
            if manual_frac > 0.5 or abs(math.log(s / s_eye)) > math.log(1.3):
                scale_note = f"   scale from GPS {s:.3f} REPLACED by eye-height scale {s_eye:.3f} (camera {h_med:.2f} m up in the GPS-only frame)"
                s = s_eye
                t = np.array([t[0], t[1], -s * float((R @ cams[idx].mean(0))[2])])
            else:
                scale_note = f"   eye-height scale would be {s_eye:.3f}, agrees"
        rej = idx[w < 0.2]
        trusted = res[w >= 0.99]
        manual = [int(i) for i, tg in zip(idx, ptags) if tg == "manual"]
        kept_txt = (f"GPS residual on trusted frames median {np.median(trusted):.1f} m "
                    f"p90 {np.percentile(trusted, 90):.1f} m" if len(trusted) else "no fully-trusted frames")
        print(f"  span {si}: frames {a0}-{a1} ({len(idx)})  scale {s:.3f} m/unit  {kept_txt}"
              + (f"   manual on {len(manual)}" if manual else "")
              + (f"   GPS DISTRUSTED on {len(rej)} frame(s): {rej.tolist()}" if len(rej) else "")
              + scale_note)
        out.append({"span": si, "frames": [int(a0), int(a1)], "scale_units_per_m": float(s),
                    "R": R.tolist(), "t": t.tolist(),
                    "gps_distrusted": rej.tolist(), "manual": manual,
                    "residual_m": {int(i): round(float(r), 2) for i, r in zip(idx, res)}})
    if a.json:
        json.dump({"up": up.tolist(), "up_source": ev["up_source"], "spans": out}, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
