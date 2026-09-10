#!/usr/bin/env python3
"""Join separately solved spans by the geometry they share, and put the GPS join on trial.

WHY. A walk that breaks into spans (a swipe, a staircase, a manual-location block) is now
solved as several child runs, each internally sound. Registering them back into one model
by GPS alone is what `recon_spans.py` does, and GPS is the weakest instrument we have: a few
metres of position, a heading that wanders, no scale at all on a short span. But the parent
run already PAID for correspondences that cross the break (its pairing window does not know
about breaks), and they sit in the shared cache addressed by image content. Each such pair
sees the same physical surface from a frame of span A and a frame of span B; both spans know
where that surface is in their own coordinates (their dense depth), so every cross pair is a
3-D <-> 3-D registration problem with a closed-form answer (Umeyama), scale included.

WHAT IT DOES.
  1. For every pair of runs, every cross pair with cached correspondences: back-project the
     matched pixels through each run's own depth and poses -> two point sets of the same
     surface, one in each run's frame. RANSAC a similarity between them.
  2. Pool the inliers of every cross pair and fit ONE similarity B->A (IRLS). A cross pair
     whose own similarity disagrees with the pooled one (rotation, scale) is reported as
     'contradicts' -- the same idea as the two-view verifier, one level up.
  3. Compare the geometric join with the GPS join implied by the two runs' own alignments:
     how many degrees, what scale ratio, how many metres apart they put span B. That number
     is the verdict on the GPS registration.

Usage:
  recon_join_spans.py <run_dir_A> <run_dir_B> [more run dirs] [--parent DIR] [--json out]
  recon_join_spans.py --self-test    # dense-spotA vs spotA-win12: the same 46 frames solved
                                     # twice must join with camera centres coinciding

The first run dir is the reference frame. Extra correspondence caches (a parent run's
masked copies) are searched before the shared cache when --parent is given. Read-only.
"""
import argparse
import glob
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recon_metrics as rm       # noqa: E402


# ---------- similarity fitting ----------
def umeyama(src, dst, w=None):
    """Weighted similarity dst ≈ s·R·src + t. Returns (s, R, t)."""
    src = np.asarray(src, float); dst = np.asarray(dst, float)
    if w is None:
        w = np.ones(len(src))
    w = np.asarray(w, float); w = w / max(w.sum(), 1e-12)
    ms = (w[:, None] * src).sum(0); md = (w[:, None] * dst).sum(0)
    S = src - ms; D = dst - md
    cov = (w[:, None] * D).T @ S
    U, d, Vt = np.linalg.svd(cov)
    Sg = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        Sg[2, 2] = -1
    R = U @ Sg @ Vt
    var_s = (w * (S ** 2).sum(1)).sum()
    s = float(np.trace(np.diag(d) @ Sg) / max(var_s, 1e-12))
    t = md - s * R @ ms
    return s, R, t


def apply(sim, p):
    s, R, t = sim
    return s * (np.asarray(p) @ R.T) + t


def compose(outer, inner):
    """outer ∘ inner : p -> outer(inner(p))."""
    s1, R1, t1 = inner; s2, R2, t2 = outer
    return s2 * s1, R2 @ R1, s2 * (R2 @ t1) + t2


def invert(sim):
    s, R, t = sim
    return 1.0 / s, R.T, -(R.T @ t) / s


def rot_angle_deg(R):
    return math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))


def ransac_similarity(P, Q, thr, iters=300, seed=0):
    """Similarity Q ≈ S(P) robust to wrong matches and bad depth. thr in Q's units."""
    rng = np.random.default_rng(seed)
    n = len(P)
    if n < 4:
        return None, np.zeros(n, bool)
    best, best_inl = None, np.zeros(n, bool)
    for _ in range(iters):
        idx = rng.choice(n, 3, replace=False)
        p, q = P[idx], Q[idx]
        # degenerate (collinear) sample: skip
        if np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) < 1e-9:
            continue
        sim = umeyama(p, q)
        if not (0.2 < sim[0] < 5.0):
            continue
        r = np.linalg.norm(apply(sim, P) - Q, axis=1)
        inl = r < thr
        if inl.sum() > best_inl.sum():
            best, best_inl = sim, inl
    if best is None or best_inl.sum() < 4:
        return None, best_inl
    # refine on inliers, twice
    for _ in range(2):
        best = umeyama(P[best_inl], Q[best_inl])
        r = np.linalg.norm(apply(best, P) - Q, axis=1)
        best_inl = r < thr
    return best, best_inl


def irls_similarity(P, Q, w0=None, iters=8):
    w = np.ones(len(P)) if w0 is None else np.asarray(w0, float).copy()
    sim = umeyama(P, Q, w)
    for _ in range(iters):
        r = np.linalg.norm(apply(sim, P) - Q, axis=1)
        mad = np.median(r) * 1.4826 + 1e-9
        w = (w0 if w0 is not None else 1.0) / (1.0 + (r / (3 * mad)) ** 2)
        sim = umeyama(P, Q, w)
    r = np.linalg.norm(apply(sim, P) - Q, axis=1)
    return sim, r


# ---------- a solved run ----------
class Run:
    def __init__(self, rundir):
        self.dir = rundir
        self.name = os.path.basename(rundir.rstrip("/"))
        self.meta = json.load(open(os.path.join(rundir, "metadata.json")))
        self.frames = self.meta["frames"]
        self.ids = [f["id"] for f in self.frames]
        self.keys = rm.frame_keys(self.meta)          # this run's own cache (canon views)
        self.ckeys = rm.content_keys(self.meta, rundir)  # the shared cache
        scene = np.load(os.path.join(rundir, "scene.npz"))
        self.poses = scene["poses"].astype(np.float64)            # cam2world, solve units
        self.K = (scene["intrinsics"].astype(np.float64) if "intrinsics" in scene.files
                  else rm.intrinsics(scene["focals"].astype(np.float64).ravel(), *self._hw()[::-1]))
        dense = np.load(os.path.join(rundir, "dense.npz"), allow_pickle=True)
        self.depth = [np.asarray(d, np.float64).ravel() for d in dense["depthmaps"]]
        self.H, self.W, _ = self._hw_from_canon()
        al = self.meta.get("alignment") or {}
        # solve -> ENU (metres): p_enu = s·R·p + t, s in metres per unit
        self.to_enu = (float(al["scale_units_per_m"]), np.asarray(al["R"], float),
                       np.asarray(al["t"], float)) if al else None

    def _hw(self):
        return self._hw_from_canon()[:2]

    def _hw_from_canon(self):
        H, W, bf = rm.read_frame_geometry(rm.canon_paths(self.dir, self.keys))
        if (H == 0).any():
            # no canonical views (a run whose cache is gone): infer from the depth size + K
            n = len(self.depth[0])
            for i in range(len(H)):
                if H[i] == 0:
                    cx, cy = self.K[i][0, 2], self.K[i][1, 2]
                    W[i] = int(round(2 * cx)); H[i] = n // max(W[i], 1)
        return H, W, bf

    def cam_centres(self):
        return self.poses[:, :3, 3]

    def points_for(self, i, xy):
        """Matched pixels (col,row) of frame i -> 3-D in this run's world, via its depth.
        Returns (pts, ok) with ok False where the depth is missing."""
        W, H = int(self.W[i]), int(self.H[i])
        u = np.clip(np.round(xy[:, 0]).astype(int), 0, W - 1)
        v = np.clip(np.round(xy[:, 1]).astype(int), 0, H - 1)
        d = self.depth[i]
        if d.size != W * H:
            return np.zeros((len(xy), 3)), np.zeros(len(xy), bool)
        z = d[v * W + u]
        ok = np.isfinite(z) & (z > 0)
        K = self.K[i]
        x = (u - K[0, 2]) / K[0, 0] * z
        y = (v - K[1, 2]) / K[1, 1] * z
        pc = np.stack([x, y, z], 1)
        pw = pc @ self.poses[i][:3, :3].T + self.poses[i][:3, 3]
        return pw, ok


# ---------- cross correspondences ----------
def corres_dirs(runs, parent=None):
    dirs = []
    for r in ([parent] if parent else []) + [x.dir for x in runs]:
        dirs += glob.glob(os.path.join(r, "cache", "corres_masked_conf=*"))
    for r in runs:
        dirs += glob.glob(os.path.join(r.dir, "cache", "corres_conf=*"))
    shared = rm.shared_cache_dir(runs[0].dir)
    if shared:
        dirs += glob.glob(os.path.join(shared, "corres_conf=*"))
    return dirs


def find_corres(dirs, k1, k2):
    """→ (xy1, xy2, conf) for the ordered pair (k1,k2), from whichever cache has it."""
    for d in dirs:
        f = os.path.join(d, f"{k1}-{k2}.pth")
        if os.path.exists(f):
            _s, (xy1, xy2, c) = rm._load_pth(f)
            return rm._np(xy1).astype(float), rm._np(xy2).astype(float), rm._np(c).ravel()
        f = os.path.join(d, f"{k2}-{k1}.pth")
        if os.path.exists(f):
            _s, (xy2, xy1, c) = rm._load_pth(f)
            return rm._np(xy1).astype(float), rm._np(xy2).astype(float), rm._np(c).ravel()
    return None


# ---------- the join ----------
def join_pair(A, B, dirs, min_corres=60, conf_thr=rm.CONF_THR, rel_thr=0.05, log=print):
    """Similarity B->A from every cross pair with cached correspondences.
    Returns dict with the pooled similarity, per-pair rows, and the GPS comparison."""
    rows, pooled_P, pooled_Q, pooled_w = [], [], [], []
    n_cand = n_have = 0
    for i, ka in enumerate(A.ckeys):
        for j, kb in enumerate(B.ckeys):
            if ka is None or kb is None:
                continue
            if A.ids[i] == B.ids[j]:
                continue
            n_cand += 1
            c = find_corres(dirs, ka, kb)
            if c is None:
                continue
            n_have += 1
            xy1, xy2, conf = c
            keep = conf >= conf_thr
            if keep.sum() < min_corres:
                continue
            xy1, xy2, conf = xy1[keep], xy2[keep], conf[keep]
            Pa, oka = A.points_for(i, xy1)
            Pb, okb = B.points_for(j, xy2)
            ok = oka & okb
            if ok.sum() < min_corres:
                continue
            Pa, Pb, conf = Pa[ok], Pb[ok], conf[ok]
            # threshold relative to how far the surface is from camera a: depth error scales
            # with depth, and a 5 % of-range residual is about what MASt3R depth is good for
            rng_a = np.median(np.linalg.norm(Pa - A.poses[i][:3, 3], axis=1))
            sim, inl = ransac_similarity(Pb, Pa, thr=rel_thr * rng_a)
            row = dict(a=i, b=j, a_id=A.ids[i][:8], b_id=B.ids[j][:8], n=int(len(Pa)),
                       inliers=int(inl.sum()), inlier_frac=float(inl.mean()) if len(inl) else 0.0)
            if sim is not None:
                row.update(scale=float(sim[0]), rot_deg=float(rot_angle_deg(sim[1])))
                pooled_P.append(Pb[inl]); pooled_Q.append(Pa[inl]); pooled_w.append(conf[inl])
                row["_sim"] = sim
            rows.append(row)
    out = dict(n_candidate_pairs=n_cand, n_cached_pairs=n_have, n_usable_pairs=len(rows))
    if not pooled_P:
        out.update(status="no usable cross pairs", pairs=[_public(r) for r in rows])
        return out
    P = np.concatenate(pooled_P); Q = np.concatenate(pooled_Q); w = np.concatenate(pooled_w)
    sim, r = irls_similarity(P, Q, w)
    out["similarity_B_to_A"] = dict(scale=float(sim[0]), R=sim[1].tolist(), t=sim[2].tolist())
    out["pooled_points"] = int(len(P))
    out["pooled_residual_units"] = dict(median=float(np.median(r)), p90=float(np.percentile(r, 90)))
    # per-pair verdicts against the pooled answer
    for row in rows:
        ps = row.pop("_sim", None)
        if ps is None:
            row["verdict"] = "no-geometry"
            continue
        dR = rot_angle_deg(ps[1].T @ sim[1])
        ds = abs(math.log(ps[0] / sim[0]))
        row["vs_pooled_rot_deg"] = float(dR); row["vs_pooled_scale_ratio"] = float(math.exp(ds))
        row["verdict"] = ("verified" if (dR < 5 and ds < math.log(1.15) and row["inliers"] >= 30)
                          else "contradicts" if row["inliers"] >= 30 else "weak")
    out["verdicts"] = {v: sum(1 for x in rows if x["verdict"] == v)
                       for v in ("verified", "weak", "contradicts", "no-geometry")}
    out["pairs"] = [_public(x) for x in rows]
    # the GPS join, for comparison: A.to_enu^-1 ∘ B.to_enu maps B's solve frame into A's
    if A.to_enu and B.to_enu:
        gps = compose(invert(A.to_enu), B.to_enu)
        dR = rot_angle_deg(gps[1].T @ sim[1])
        cB = B.cam_centres()
        d = np.linalg.norm(apply(sim, cB) - apply(gps, cB), axis=1) * A.to_enu[0]
        out["gps_join"] = dict(scale=float(gps[0]), rot_deg_vs_geometric=float(dR),
                               scale_ratio_vs_geometric=float(sim[0] / gps[0]),
                               camera_displacement_m=dict(median=float(np.median(d)),
                                                          max=float(d.max())))
    # shared photos (a self-test, or overlapping spans): where do the two solves put them?
    common = [(i, B.ids.index(a)) for i, a in enumerate(A.ids) if a in B.ids]
    if common and A.to_enu:
        ca = np.array([A.cam_centres()[i] for i, _ in common])
        cb = apply(sim, np.array([B.cam_centres()[j] for _, j in common]))
        d = np.linalg.norm(ca - cb, axis=1) * A.to_enu[0]
        out["shared_frames"] = dict(n=len(common), centre_gap_m=dict(
            median=float(np.median(d)), p90=float(np.percentile(d, 90)), max=float(d.max())))
    out["status"] = "ok"
    return out


def _public(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def summarize(res, A, B, log=print):
    log(f"{B.name} -> {A.name}: {res['n_cached_pairs']}/{res['n_candidate_pairs']} cross pairs "
        f"cached, {res['n_usable_pairs']} usable")
    if res.get("status") != "ok":
        log(f"  {res.get('status')}")
        return
    s = res["similarity_B_to_A"]
    log(f"  pooled similarity from {res['pooled_points']} points: scale {s['scale']:.3f}, "
        f"residual median {res['pooled_residual_units']['median']:.3f} units; "
        f"verdicts {res['verdicts']}")
    g = res.get("gps_join")
    if g:
        log(f"  GPS join differs by {g['rot_deg_vs_geometric']:.1f}°, scale ×{g['scale_ratio_vs_geometric']:.3f}, "
            f"cameras displaced median {g['camera_displacement_m']['median']:.2f} m "
            f"(max {g['camera_displacement_m']['max']:.2f} m)")
    sf = res.get("shared_frames")
    if sf:
        log(f"  {sf['n']} shared photos: centre gap median {sf['centre_gap_m']['median']:.2f} m, "
            f"p90 {sf['centre_gap_m']['p90']:.2f} m, max {sf['centre_gap_m']['max']:.2f} m")


def self_test():
    here = os.path.dirname(os.path.abspath(__file__))
    bench = os.path.join(here, "runs", "bench")
    A = Run(os.path.join(bench, "89f43149-cd32-4418-8004-d13782ce28fa"))   # dense-spotA-2026-08-19
    B = Run(os.path.join(bench, "994e0c13-9b29-4a47-88a3-d08381416345"))   # spotA-win12
    res = join_pair(A, B, corres_dirs([A, B]))
    summarize(res, A, B)
    ok = res.get("status") == "ok" and res["shared_frames"]["centre_gap_m"]["median"] < 0.5
    print("self-test", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--parent", help="run dir whose (masked) correspondence cache to search first")
    ap.add_argument("--json")
    ap.add_argument("--min-corres", type=int, default=60)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if len(a.runs) < 2:
        ap.error("two or more run dirs")
    runs = [Run(r) for r in a.runs]
    dirs = corres_dirs(runs, a.parent)
    A = runs[0]
    out = {"reference": A.name, "joins": {}}
    for B in runs[1:]:
        res = join_pair(A, B, dirs, a.min_corres)
        summarize(res, A, B)
        out["joins"][B.name] = res
    if len(runs) > 2:
        # spans that do not touch the reference may still touch each other
        for x in range(1, len(runs)):
            for y in range(x + 1, len(runs)):
                res = join_pair(runs[x], runs[y], dirs, a.min_corres)
                summarize(res, runs[x], runs[y])
                out["joins"][f"{runs[y].name}->{runs[x].name}"] = res
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
