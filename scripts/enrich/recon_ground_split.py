#!/usr/bin/env python3
"""How many floors does this run think there are?

The model of a flat plaza came out with a second slab of pavement 28 cm below the real
one, and a gravel path came out as a staircase of tiles. Both are the same defect: each
frame's own depth is fine locally, but successive frames disagree about where the ground
is, so the fused cloud stacks them.

This unprojects every frame's OWN depthmap, keeps the points that are plausibly the floor
beneath that frame's camera, and reports the height each frame puts it at. Frames agreeing
to a few centimetres means one floor; a spread means as many floors as there are clusters,
and the offenders are named.

Usage:  python recon_ground_split.py <run_dir> [--json out.json]
Read-only; needs dense.npz, so it runs where the solve ran.
"""
import argparse
import json
import os

import numpy as np


def analyse(run_dir, stride=3, log=print):
    """The measurement as a dict; see the module docstring for what the numbers mean."""
    a = argparse.Namespace(run_dir=run_dir, stride=stride, json=None)
    return _run(a, log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--json")
    ap.add_argument("--stride", type=int, default=3, help="pixel stride, for memory")
    a = ap.parse_args()
    out = _run(a, print)
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print("wrote", a.json)


def _run(a, print):
    z = np.load(os.path.join(a.run_dir, "dense.npz"), allow_pickle=True)
    md = json.load(open(os.path.join(a.run_dir, "metadata.json")))
    al = md["alignment"]
    s, R, t = al["scale_units_per_m"], np.array(al["R"]), np.array(al["t"])
    D = z["depthmaps"].astype(np.float32)
    poses = z["poses"].astype(np.float64)
    focals = z["focals"].astype(np.float64)
    n, npx = D.shape
    ow, oh = None, None
    # the loaded frame is whatever shape has npx pixels at the photos' aspect; metadata
    # keeps neither, so recover it from the run's own args.size and the depth length
    long_side = float((md.get("args") or {}).get("size") or 512)
    H = int(round((npx / (long_side / max(long_side, 1))) ** 0.5))
    for cand_h in range(int(np.sqrt(npx)), int(np.sqrt(npx) * 2) + 1):
        if npx % cand_h == 0:
            H = cand_h
            break
    W = npx // H
    vv, uu = np.mgrid[0:H, 0:W]
    uu = (uu - W / 2).ravel().astype(np.float64)[::a.stride]
    vv = (vv - H / 2).ravel().astype(np.float64)[::a.stride]

    def to_enu(P):
        return s * (P @ R.T) + t

    rows, patches, cams_xy = [], [], []
    for i in range(n):
        d = D[i].reshape(-1).astype(np.float64)[::a.stride]
        f = focals[i]
        P = np.stack([uu * d / f, vv * d / f, d], 1)
        E = to_enu((poses[i][:3, :3] @ P.T).T + poses[i][:3, 3])
        cam = to_enu(poses[i][:3, 3][None])[0]
        below = cam[2] - E[:, 2]
        rad = np.hypot(E[:, 0] - cam[0], E[:, 1] - cam[1])
        m = (below > 0.6) & (below < 3.0) & (rad < 6.0) & (vv > 0)
        cams_xy.append(cam[:2])
        if m.sum() < 200:
            rows.append({"idx": i, "n": int(m.sum()), "floor": None})
            patches.append(None)
            continue
        patches.append(E[m])
        zg = E[m, 2]
        rows.append({"idx": i, "n": int(m.sum()),
                     "floor": round(float(np.median(zg)), 4),
                     "cam_height": round(float(cam[2] - np.median(zg)), 3)})
    have = [r for r in rows if r["floor"] is not None]
    if not have:
        print("no frame has ground beneath it")
        return {"camera_height_m": None, "frames": rows}
    ch = np.array([r["cam_height"] for r in have])
    print(f"{len(have)}/{n} frames with a floor beneath them")
    print(f"camera height above ITS OWN floor: median {np.median(ch):.2f} m  sd {ch.std():.2f} m"
          f"   (a phone is held at 1.4-1.7 m, so the median is also a scale check)")

    # A single "consensus floor" only means something for a capture that stood still; a
    # walk climbs and descends, and its floor is supposed to move. What must hold either
    # way is that two frames looking at the SAME patch of ground agree on its height.
    span = float(np.ptp(np.array(cams_xy), axis=0).max()) if cams_xy else 0.0
    static = span < 15.0
    v = np.array([r["floor"] for r in have])
    if static:
        cons = float(np.median(v))
        off = v - cons
        thr = max(0.08, 3 * float(np.median(np.abs(off))))
        bad = [r for r, o in zip(have, off) if abs(o) > thr]
        print(f"stationary capture: consensus floor {cons:+.3f} m, sd {v.std():.3f} m")
        print(f"frames more than {thr*100:.0f} cm off it: {len(bad)}")
        for r, o in sorted(zip(have, off), key=lambda x: x[1]):
            if abs(o) > thr:
                print(f"   frame {r['idx']:3d}  floor {r['floor']:+.3f} ({o*100:+5.0f} cm)")
    else:
        print(f"moving capture: floor ranges {v.min():+.2f}..{v.max():+.2f} m, "
              f"which is the terrain, not an error")

    # The staircase test, and the one that works for both: over the ground each pair of
    # neighbouring frames BOTH see, do they put it at the same height?
    steps = []
    for k in range(len(patches) - 1):
        A, B = patches[k], patches[k + 1]
        if A is None or B is None:
            continue
        mid = (cams_xy[k] + cams_xy[k + 1]) / 2.0
        sa = A[np.hypot(A[:, 0] - mid[0], A[:, 1] - mid[1]) < 2.0]
        sb = B[np.hypot(B[:, 0] - mid[0], B[:, 1] - mid[1]) < 2.0]
        if len(sa) < 60 or len(sb) < 60:
            continue
        steps.append((k, float(np.median(sb[:, 2]) - np.median(sa[:, 2]))))
    if steps:
        d = np.abs([x[1] for x in steps])
        print(f"\nneighbouring frames disagreeing about the SAME patch of ground: "
              f"{len(steps)} overlaps")
        print(f"  |step| median {np.median(d)*100:5.1f} cm   p90 {np.percentile(d, 90)*100:5.1f} cm"
              f"   max {d.max()*100:5.1f} cm")
        worst = sorted(steps, key=lambda x: -abs(x[1]))[:6]
        print("  worst: " + "  ".join(f"{k}->{k+1}:{v*100:+.0f}cm" for k, v in worst))
    d = np.abs([x[1] for x in steps]) if steps else np.array([])
    return {"camera_height_m": round(float(np.median(ch)), 3),
            "camera_height_sd_m": round(float(ch.std()), 3),
            "stationary": bool(static),
            "neighbour_step_cm": ({"median": round(float(np.median(d)) * 100, 1),
                                   "p90": round(float(np.percentile(d, 90)) * 100, 1),
                                   "max": round(float(d.max()) * 100, 1), "n": int(len(d))}
                                  if len(d) else None),
            "frames": rows}


if __name__ == "__main__":
    main()
