#!/usr/bin/env python3
"""
recon_resolve — recover a run's EXACT intrinsics (and, if missing, its depthmaps) by
re-solving from its intact forward-pass cache.

WHY. reconstruct.py saves poses and focals but not principal points, even though
sparse_ga optimizes them (opt_pp=True). recon_metrics must otherwise put pp at the image
centre, and that approximation is not small: on masktest the true pps sit 4-6 px off
centre, which inflates the reprojection metric from 0.71 px to 3.57 px. Since the metric
is itself measured in pixels, absolute claims are worthless without the true pps.

HOW. The solve is deterministic given the cache: re-solving masktest reproduced the
archived focals exactly and the camera centres to a max delta of 0. The expensive part
(the ~32 s/pair forward passes) is cached, so only the 300+300 optimizer iterations run.
This tool re-solves, checks it reproduced the archived poses, and writes a sidecar
`intrinsics.npz` that recon_metrics picks up automatically. The archived artifacts are
never modified.

Pairs must be built by make_pairs exactly as the run built them, NOT hand-assembled from
the cache: pair ORDER feeds the kinematic chain (MST/hclust over pairwise scores), so a
re-ordered but otherwise identical pair set can land in a different local minimum — on
masktest that produced a solve whose cameras sat 264% of the scene extent away from the
archived ones. So the mode is taken from metadata args (the oldest runs predate the
--pairs flag and used swin), and the cache is used to VERIFY the pair set matches.

    .venv/bin/python recon_resolve.py runs/walk_dense
    .venv/bin/python recon_resolve.py runs/walk_sparse --depth   # also materialize depth
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MAST3R_REPO = os.getenv("MAST3R_REPO", os.path.join(HERE, "mast3r_repo"))
MAST3R_CKPT = os.getenv("MAST3R_CKPT", os.path.join(MAST3R_REPO, "checkpoints", "mast3r.pth"))

import recon_metrics as RM  # noqa: E402  (same dir; hash keying + readers live there)


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def cached_pair_indices(rundir, keys):
    """Ordered (i, j) pairs that were actually solved, read off the corres cache."""
    idx = {k: i for i, k in enumerate(keys)}
    out = set()
    for d in glob.glob(os.path.join(rundir, "cache", "corres_conf=*")):
        for f in glob.glob(os.path.join(d, "*.pth")):
            name = os.path.splitext(os.path.basename(f))[0]
            if "-" not in name:
                continue
            h1, h2 = name.split("-", 1)
            if h1 in idx and h2 in idx:
                out.add((idx[h1], idx[h2]))
    return sorted(out)


def resolve(rundir, want_depth=False, device="cpu"):
    meta = json.load(open(os.path.join(rundir, "metadata.json")))
    frames = meta["frames"]
    out_arg = meta["args"]["out"]
    size = int(meta["args"].get("size", 512))

    # The path STRINGS are the cache keys, so they must be exactly what the run used.
    paths = [os.path.join(out_arg, "imgs", f"{f['idx']:03d}_{f['id'][:8]}.jpg")
             for f in frames]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise SystemExit(
            f"{rundir}: {len(missing)} frame image(s) missing, e.g. {missing[0]!r}. "
            f"Run this from {HERE} so the run-time relative paths resolve.")

    keys = RM.frame_keys(meta)
    cached = set(cached_pair_indices(rundir, keys))
    if not cached:
        raise SystemExit(f"{rundir}: no resolvable correspondence cache — nothing to re-solve")

    for p in (MAST3R_REPO, os.path.join(MAST3R_REPO, "dust3r"),
              os.path.join(MAST3R_REPO, "dust3r", "croco")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from dust3r.image_pairs import make_pairs
    from dust3r.utils.image import load_images
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment
    from mast3r.model import AsymmetricMASt3R

    log(f"{rundir}: {len(paths)} frames, {len(cached)} cached pairs")
    model = AsymmetricMASt3R.from_pretrained(MAST3R_CKPT).to(device).eval()
    imgs = load_images(paths, size=size, verbose=False)

    mode = meta["args"].get("pairs", "swin")   # walk_dense/walk_sparse predate the flag
    if mode == "complete":
        pairs = make_pairs(imgs, scene_graph="complete", prefilter=None, symmetrize=True)
    else:
        if mode not in ("swin", None):
            log(f"  note: args.pairs={mode!r}; reproducing as swin and verifying "
                f"against the cache")
        win = min(int(meta["args"].get("win", 3)), len(imgs) - 1)
        pairs = make_pairs(imgs, scene_graph=f"swin-{win}-noncyclic", prefilter=None,
                           symmetrize=True)
    built = {(a["idx"], b["idx"]) for a, b in pairs}
    if built != cached:
        raise SystemExit(
            f"{rundir}: rebuilt pair set does not match the cache "
            f"({len(built)} built vs {len(cached)} cached; "
            f"{len(built - cached)} extra, {len(cached - built)} missing). The re-solve "
            f"would not reproduce the archived solve — fix the pairing mode first.")
    log(f"  pair set matches the cache ({mode}, {len(pairs)} pairs)")

    t0 = time.time()
    scene = sparse_global_alignment(
        paths, pairs, os.path.join(rundir, "cache"), model,
        lr1=0.07, niter1=int(meta["args"].get("niter1", 300)),
        lr2=0.01, niter2=int(meta["args"].get("niter2", 300)),
        device=device, matching_conf_thr=5.0, shared_intrinsics=False)
    log(f"  re-solve took {time.time() - t0:.0f}s")

    K = scene.intrinsics.detach().cpu().numpy().astype(np.float64)
    poses = scene.get_im_poses().detach().cpu().numpy().astype(np.float64)
    focals = scene.get_focals().detach().cpu().numpy().ravel().astype(np.float64)

    # Did we reproduce the archived solve? The comparison MUST be gauge-invariant: a
    # reconstruction is only defined up to a global similarity, so comparing raw
    # coordinates is meaningless. walk_dense's re-solve looked 140% of the scene extent
    # away by raw coordinates and is actually the same reconstruction — 0.67% of extent
    # once Umeyama-aligned, with a 0.22% global scale difference. Focals ARE gauge-
    # invariant, so they are compared directly.
    sc = np.load(os.path.join(rundir, "scene.npz"))
    old_cams = sc["poses"][:, :3, 3].astype(np.float64)
    new_cams = poses[:, :3, 3]
    d_focal = float(np.abs(sc["focals"].ravel().astype(np.float64) - focals).max())
    rel_focal = float(np.abs((sc["focals"].ravel().astype(np.float64) - focals)
                             / np.maximum(sc["focals"].ravel().astype(np.float64), 1e-9)).max())
    extent = float(np.ptp(old_cams, axis=0).max()) or 1.0
    s_align, R_align, t_align = RM.umeyama(new_cams, old_cams)
    aligned = (s_align * (R_align @ new_cams.T)).T + t_align
    rms = float(np.sqrt(((aligned - old_cams) ** 2).sum(1).mean()))
    raw = float(np.abs(old_cams - new_cams).max())
    log(f"  vs archived solve (gauge-invariant): aligned camera RMS = {rms:.4g} units "
        f"({100 * rms / extent:.3g}% of extent), global scale {s_align:.5f}, "
        f"max |dfocal| = {d_focal:.4g} px ({100 * rel_focal:.2f}%)")
    log(f"    (raw coordinate delta was {100 * raw / extent:.3g}% of extent — gauge, "
        f"not structure)")
    faithful = rms < 0.02 * extent and rel_focal < 0.05
    if not faithful:
        log("  WARNING: the re-solve is genuinely a different reconstruction — treat the "
            "recovered intrinsics as belonging to it, not to the archived run")

    payload = {"K": K, "poses": poses, "focals": focals,
               "pps_px": K[:, 0:2, 2],
               "faithful": np.array(faithful),
               # maps THIS solve's units into the archived solve's units, so archived
               # depthmaps can be used with these poses without a scale mismatch
               "scale_to_archived": np.array(s_align),
               "aligned_rms_frac_extent": np.array(rms / extent),
               "d_focal_px": np.array(d_focal), "rel_focal": np.array(rel_focal)}

    if want_depth:
        log("  extracting per-pixel depth (get_dense_pts3d)…")
        t0 = time.time()
        _pts, depths, _confs = scene.get_dense_pts3d(clean_depth=True)
        dm = [np.asarray(d.detach().cpu().numpy() if hasattr(d, "detach") else d,
                         dtype=np.float32).ravel() for d in depths]
        payload["depthmaps"] = np.array(dm, dtype=object)
        log(f"  depth for {len(dm)} frames in {time.time() - t0:.0f}s")

    return payload


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rundirs", nargs="+")
    ap.add_argument("--depth", action="store_true",
                    help="also extract per-pixel depthmaps (for runs solved without --dense)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default="intrinsics.npz",
                    help="sidecar filename written inside each run dir")
    a = ap.parse_args()
    for d in a.rundirs:
        d = d.rstrip("/")
        payload = resolve(d, want_depth=a.depth, device=a.device)
        p = os.path.join(d, a.out)
        np.savez_compressed(p, **payload)
        log(f"  wrote {p}")


if __name__ == "__main__":
    main()
