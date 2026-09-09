#!/usr/bin/env python3
"""Judge each image pair on its OWN evidence, independent of the global solve.

WHY. `fuse-prosek-5sessions` showed that throwing five visits into one joint solve does
not merely fail on the cross-visit links -- it wrecks the within-visit geometry too, from
12 px per pair to 144. And the per-pair numbers that come out of a broken joint solve
cannot then be used to decide which links were the bad ones, because they mix "this match
is wrong" with "this solve is wrong". A correspondence-count gate does not rescue it
either: at Prosek, pairs with 3,000+ correspondences still sat at 92 px median, and one
with 3,151 reached 7,697 px. Confidence is not correctness -- the same lesson the printed
Doppelganger board taught while carrying 1,012 correspondences.

So a link has to be judged BEFORE any global optimisation touches it, from the two views
alone:

  1. normalise the cached correspondences by each frame's own intrinsics,
  2. RANSAC an essential matrix (8-point on calibrated coordinates, Sampson distance),
  3. keep the inlier ratio -- a true pair of views of one place has a consistent epipolar
     geometry, a false match has none, however many points it produced,
  4. decompose E, pick the (R, t) with the most points in front of both cameras, and
  5. check the recovered baseline DIRECTION against the direction GPS puts between the two
     cameras. A true link agrees; a Doppelganger has no reason to.

Step 5 is what makes this more than a repeat of the epipolar metric: it brings in evidence
from outside the images.

Usage:  python recon_verify_links.py <run_dir> [--json out.json] [--min-corres 60]
Read-only. Needs the run's cache/, so it runs where the solve ran.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recon_metrics as rm       # noqa: E402  (path set above)


def cam2world_from_heading(heading_deg):
    """A level camera at this compass heading, in the x-right / y-down / z-forward frame.

    Columns are right, down, forward in ENU. Pitch is ignored: the check only needs the
    horizontal direction, and a phone tilted down still points the same way.
    """
    h = math.radians(heading_deg)
    return np.array([[math.cos(h), 0.0, math.sin(h)],
                     [-math.sin(h), 0.0, math.cos(h)],
                     [0.0, -1.0, 0.0]])


def sampson(E, x1, x2):
    """Sampson distance in CALIBRATED units (multiply by focal for pixels)."""
    Ex1 = x1 @ E.T
    Etx2 = x2 @ E
    num = np.einsum("ij,ij->i", x2, Ex1) ** 2
    den = Ex1[:, 0] ** 2 + Ex1[:, 1] ** 2 + Etx2[:, 0] ** 2 + Etx2[:, 1] ** 2
    return num / np.maximum(den, 1e-12)


def eight_point(x1, x2):
    """x1, x2 are calibrated homogeneous points, (n, 3) with z == 1."""
    A = np.stack([x2[:, 0] * x1[:, 0], x2[:, 0] * x1[:, 1], x2[:, 0],
                  x2[:, 1] * x1[:, 0], x2[:, 1] * x1[:, 1], x2[:, 1],
                  x1[:, 0], x1[:, 1], np.ones(len(x1))], 1)
    _, _, vt = np.linalg.svd(A)
    E = vt[-1].reshape(3, 3)
    u, s, vt2 = np.linalg.svd(E)
    # an essential matrix has two equal singular values and a zero: enforce it
    return u @ np.diag([1.0, 1.0, 0.0]) @ vt2


def ransac_E(x1, x2, thr, iters=600, seed=0):
    rng = np.random.default_rng(seed)
    n = len(x1)
    if n < 12:
        return None, np.zeros(n, bool)
    best = (0, None)
    for _ in range(iters):
        i = rng.choice(n, 8, replace=False)
        try:
            E = eight_point(x1[i], x2[i])
        except np.linalg.LinAlgError:
            continue
        inl = sampson(E, x1, x2) < thr ** 2
        c = int(inl.sum())
        if c > best[0]:
            best = (c, E)
    if best[1] is None:
        return None, np.zeros(n, bool)
    inl = sampson(best[1], x1, x2) < thr ** 2
    if inl.sum() >= 8:                     # refit on the consensus set
        E = eight_point(x1[inl], x2[inl])
        inl2 = sampson(E, x1, x2) < thr ** 2
        if inl2.sum() >= inl.sum():
            return E, inl2
    return best[1], inl


def decompose(E, x1, x2, inl):
    """The (R, t) of the four candidates with the most points in front of both cameras."""
    u, _, vt = np.linalg.svd(E)
    if np.linalg.det(u) < 0:
        u = -u
    if np.linalg.det(vt) < 0:
        vt = -vt
    W = np.array([[0.0, -1, 0], [1, 0, 0], [0, 0, 1]])
    t = u[:, 2]
    best = (-1, None, None)
    d1_all, d2_all = x1[inl], x2[inl]      # already homogeneous, z == 1
    for R in (u @ W @ vt, u @ W.T @ vt):
        for tt in (t, -t):
            # E = [t]x R with x2 = R x1 + t, so camera 2's CENTRE sits at -R^T t in
            # camera 1's frame. That vector, not t, is the baseline the rays close on --
            # using t here silently picks the mirrored solution and every recovered
            # baseline comes out pointing the wrong way.
            b = -(tt @ R)
            d1 = d1_all
            d2 = d2_all @ R
            cross = np.cross(d1, d2)
            denom = (cross ** 2).sum(1)
            ok = denom > 1e-12
            if not ok.any():
                continue
            s1 = np.einsum("ij,ij->i", np.cross(b[None, :], d2), cross) / np.maximum(denom, 1e-12)
            s2 = np.einsum("ij,ij->i", np.cross(b[None, :], d1), cross) / np.maximum(denom, 1e-12)
            good = int(((s1 > 0) & (s2 > 0) & ok).sum())
            if good > best[0]:
                best = (good, R, tt)
    return best[1], best[2], best[0]


def self_test():
    """Synthesise two cameras with a known baseline and check the direction comes back.

    A sign slip in the decomposition is invisible on real data -- every link simply reads
    as contradicting GPS -- and it is exactly the mistake this file made first time round,
    so the check is wired in rather than written once and thrown away.
    """
    rng = np.random.default_rng(3)
    worst = 0.0
    for k in range(4):
        ang = math.radians(15 * (k + 1))
        c, s_ = math.cos(ang), math.sin(ang)
        R_true = np.array([[c, 0.0, s_], [0.0, 1.0, 0.0], [-s_, 0.0, c]])
        b_true = np.array([1.0, 0.0, 0.3])
        b_true /= np.linalg.norm(b_true)          # camera 2's centre in camera 1's frame
        t_true = -R_true @ b_true
        X = rng.normal(size=(400, 3))
        X[:, 2] = rng.uniform(3, 10, 400)
        x1 = X / X[:, 2:3]
        X2 = (R_true @ X.T).T + t_true
        x2 = X2 / X2[:, 2:3]
        E, inl = ransac_E(x1, x2, 1e-4, iters=300)
        R, t, ch = decompose(E, x1, x2, inl)
        b_rec = -(t @ R)
        b_rec /= np.linalg.norm(b_rec)
        err = math.degrees(math.acos(max(-1.0, min(1.0, float(b_rec @ b_true)))))
        rerr = math.degrees(np.arccos(np.clip((np.trace(R.T @ R_true) - 1) / 2, -1, 1)))
        print(f"  trial {k}: inliers {inl.mean():.2f}  cheirality {ch}/{int(inl.sum())}  "
              f"baseline dir err {err:6.2f} deg  rotation err {rerr:5.2f} deg")
        worst = max(worst, err, rerr)
    print("SELF-TEST", "PASS" if worst < 1.0 else f"FAIL (worst {worst:.2f} deg)")
    return worst < 1.0


def verdict(r):
    """The composite verdict: a link has to be self-consistent AND agree with where GPS
    and the compass say the two cameras were. Either alone is cheap to fool."""
    if r["inlier_frac"] <= 0.5 or r["cheirality_frac"] <= 0.8:
        return "no-geometry"
    d = r["baseline_dir_err_deg"]
    y = r["rel_yaw_err_deg"]
    if d is not None and d > 90:
        return "contradicts-gps"
    if y is not None and y > 60:
        return "contradicts-compass"
    return "verified"


def chain_report(rows, frames, json_path=None):
    """Where does a walk stop being one walk?

    A sliding-window solve is a chain: frame i is tied to i+1 and little else. If one link
    in that chain is weak, everything downstream of it is only held in place by GPS, and
    the reconstruction is free to fold there. Watching walk_jizni, the first five frames
    march forward and the sixth jumps back -- which is what a broken link looks like from
    the outside.

    The link strength is not the correspondence COUNT. Prosek showed pairs with 3,000+
    correspondences sitting at 92 px, so what matters is how many of them fit one epipolar
    geometry: count x inlier fraction, the number of matches that actually agree.
    """
    import numpy as np
    by = {(r["i"], r["j"]): r for r in rows}
    n = len(frames)
    links = []
    for i in range(n - 1):
        r = by.get((i, i + 1)) or by.get((i + 1, i))
        links.append((i, r))
    good = [int(round(r["n"] * r["inlier_frac"])) for _, r in links if r]
    med = float(np.median(good)) if good else 0.0
    # a break is an order of magnitude below the run's own typical link, or no link at all
    thr = max(30.0, med / 10.0)
    print(f"consecutive-frame chain over {n} frames; typical link {med:.0f} agreeing "
          f"matches, break threshold {thr:.0f}")
    breaks = []
    for i, r in links:
        g = int(round(r["n"] * r["inlier_frac"])) if r else 0
        mark = ""
        if g < thr:
            mark = "   <-- BREAK"
            breaks.append(i)
        if r:
            print(f"  {i:3d}->{i+1:<3d} matches {r['n']:5d}  inliers {r['inlier_frac']:.2f}"
                  f"  agreeing {g:5d}  {r['verdict']}{mark}")
        else:
            print(f"  {i:3d}->{i+1:<3d} no cached pair{mark}")
    if not breaks:
        print("\nno break: the chain holds all the way through")
    else:
        print(f"\n{len(breaks)} break(s) after frame(s): {breaks}")
        spans, start = [], 0
        for b in breaks:
            spans.append((start, b))
            start = b + 1
        spans.append((start, n - 1))
        print("suggested spans, to solve separately and then register as sessions:")
        for s0, s1 in spans:
            print(f"  frames {s0}-{s1}  ({s1 - s0 + 1} frames)")
    if json_path:
        json.dump({"breaks": breaks,
                   "links": [{"i": i, "agreeing": (int(round(r["n"] * r["inlier_frac"]))
                                                   if r else 0)} for i, r in links]},
                  open(json_path, "w"), indent=1)
        print("wrote", json_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--min-corres", type=int, default=60)
    ap.add_argument("--thr-px", type=float, default=2.0,
                    help="Sampson inlier threshold, in pixels of the loaded frame")
    ap.add_argument("--max-points", type=int, default=3000)
    ap.add_argument("--chain", action="store_true",
                    help="report only the CONSECUTIVE-frame chain, and where it breaks")
    a = ap.parse_args()
    if a.self_test:
        raise SystemExit(0 if self_test() else 1)
    if not a.run_dir:
        raise SystemExit("need a run_dir (or --self-test)")

    meta = json.load(open(os.path.join(a.run_dir, "metadata.json")))
    frames = meta["frames"]
    keys = rm.frame_keys(meta)
    cps = rm.canon_paths(a.run_dir, keys)
    H, W, _ = rm.read_frame_geometry(cps)
    scene = np.load(os.path.join(a.run_dir, "scene.npz"))
    focals = scene["focals"].astype(np.float64).ravel()
    K = (scene["intrinsics"].astype(np.float64) if "intrinsics" in scene.files
         else rm.intrinsics(focals, W, H))
    Kinv = np.linalg.inv(K)
    corres = rm.read_corres(a.run_dir, keys)

    lat0, lon0 = meta["center"]
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    gps = np.array([[(f["gps"][1] - lon0) * kx, (f["gps"][0] - lat0) * ky, 0.0]
                    for f in frames])
    sess = [f.get("session") for f in frames]

    rows = []
    seen = set()
    for (i, j), (xy1, xy2, confs) in sorted(corres.items()):
        if (j, i) in seen:
            continue
        seen.add((i, j))
        if len(xy1) < a.min_corres:
            continue
        sel = (np.linspace(0, len(xy1) - 1, min(a.max_points, len(xy1))).astype(int)
               if len(xy1) > a.max_points else slice(None))
        p1, p2 = xy1[sel], xy2[sel]
        x1 = (np.concatenate([p1, np.ones((len(p1), 1))], 1) @ Kinv[i].T)[:, :3]
        x2 = (np.concatenate([p2, np.ones((len(p2), 1))], 1) @ Kinv[j].T)[:, :3]
        x1 /= x1[:, 2:3]
        x2 /= x2[:, 2:3]
        thr = a.thr_px / float(np.mean([focals[i], focals[j]]))
        E, inl = ransac_E(x1, x2, thr)
        if E is None or inl.sum() < 8:
            continue
        R, t, cheir = decompose(E, x1, x2, inl)
        # baseline direction, ours vs what GPS says. Both are directions only: an
        # essential matrix has no scale, and that is fine -- the question is whether the
        # two views are looking at the same place from where GPS says they were.
        g = gps[j] - gps[i]
        gnorm = float(np.linalg.norm(g[:2]))
        ang = yaw_err = None
        bi, bj = frames[i].get("compass_angle"), frames[j].get("compass_angle")
        if gnorm > 1.0 and t is not None and bi is not None:
            # Orient by the COMPASS, not by the solved pose. Using the pose would import
            # the very solve this check exists to be independent of -- and on a fused run
            # that solve is broken. The compass is biased by tens of degrees, which is
            # fine: the signal being tested is 0 vs 180.
            tw = cam2world_from_heading(bi) @ (-R.T @ t)
            tw2 = tw[:2] / max(np.linalg.norm(tw[:2]), 1e-9)
            g2 = g[:2] / gnorm
            ang = float(np.degrees(math.acos(max(-1.0, min(1.0, float(tw2 @ g2))))))
        if bi is not None and bj is not None and R is not None:
            # relative yaw from the essential matrix vs relative yaw from the compass:
            # a second independent check, and one the compass BIAS cancels out of
            fwd = R.T @ np.array([0.0, 0.0, 1.0])
            yaw_E = math.degrees(math.atan2(fwd[0], fwd[2]))
            yaw_err = abs(((bj - bi) - yaw_E + 180) % 360 - 180)
        rows.append({"i": i, "j": j, "n": int(len(xy1)),
                     "inlier_frac": round(float(inl.mean()), 4),
                     "n_inliers": int(inl.sum()),
                     "cheirality_frac": round(cheir / max(int(inl.sum()), 1), 3),
                     "gps_dist_m": round(gnorm, 1),
                     "baseline_dir_err_deg": None if ang is None else round(ang, 1),
                     "rel_yaw_err_deg": None if yaw_err is None else round(yaw_err, 1),
                     "cross_session": bool(sess[i] and sess[j] and sess[i] != sess[j]),
                     "date_i": (frames[i].get("captured_at") or "")[:10],
                     "date_j": (frames[j].get("captured_at") or "")[:10]})

    if not rows:
        print("no pairs with enough correspondences")
        return

    for r in rows:
        r["verdict"] = verdict(r)
    if a.chain:
        chain_report(rows, frames, a.json)
        return
    fr = np.array([r["inlier_frac"] for r in rows])
    xs = np.array([r["cross_session"] for r in rows])
    print(f"{len(rows)} undirected pairs judged (>= {a.min_corres} correspondences)")
    for lab, m in (("within-session", ~xs), ("cross-session", xs)):
        if not m.any():
            continue
        v = fr[m]
        print(f"  {lab:<15} n={m.sum():4d}  inlier fraction  p10 {np.percentile(v, 10):.3f} "
              f" median {np.median(v):.3f}  p90 {np.percentile(v, 90):.3f}")
    good = [r for r in rows if r["inlier_frac"] > 0.5 and r["cheirality_frac"] > 0.8]
    print(f"  pairs with a consistent two-view geometry (inliers>50%, cheirality>80%): "
          f"{len(good)} of {len(rows)}")
    gx = [r for r in good if r["cross_session"]]
    if xs.any():
        print(f"    of which CROSS-SESSION: {len(gx)} of {int(xs.sum())}")
        for r in sorted(gx, key=lambda r: -r["inlier_frac"])[:10]:
            print(f"      {r['i']:3d}-{r['j']:3d}  n={r['n']:5d} inliers {r['inlier_frac']:.2f} "
                  f" gps {r['gps_dist_m']:5.1f} m  baseline dir err {r['baseline_dir_err_deg']}"
                  f"  rel-yaw err {r['rel_yaw_err_deg']}  {r['date_i']} <-> {r['date_j']}")
    from collections import Counter
    print("\n  verdicts:", dict(Counter(r["verdict"] for r in rows)))
    if xs.any():
        print("  cross-session verdicts:",
              dict(Counter(r["verdict"] for r in rows if r["cross_session"])))
        for r in sorted([r for r in rows if r["cross_session"] and r["verdict"] == "verified"],
                        key=lambda r: -r["inlier_frac"]):
            print(f"    VERIFIED {r['i']:3d}-{r['j']:3d}  n={r['n']:5d} inliers "
                  f"{r['inlier_frac']:.2f}  gps {r['gps_dist_m']:5.1f} m  "
                  f"{r['date_i']} <-> {r['date_j']}")
    if a.json:
        json.dump({"pairs": rows}, open(a.json, "w"), indent=1)
        print("wrote", a.json)


if __name__ == "__main__":
    main()
