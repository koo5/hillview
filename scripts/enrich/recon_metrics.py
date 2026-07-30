#!/usr/bin/env python3
"""
recon_metrics — GPS-independent structure metrics for a reconstruct.py run.

WHY THIS EXISTS. The only quality number reconstruct.py reports is the camera<->GPS
residual after a single 7-DoF Umeyama fit. That is a DRIFT GATE, not a quality score:
it catches a collapsed solve (walk_sparse, 81 m) but says almost nothing about whether
the 3-D structure is good — cameras can sit metres from the GPS track while the point
cloud is smeared. MASt3R-SfM does optimize a 2-D reprojection error internally
(sparse_ga.loss_2d) but only ever PRINTS it, as a confidence-weighted gamma loss, in
no particular unit. So we recompute honest metrics here, post hoc, in pixels.

TWO METRICS, both over the cached correspondences, both in pixels of the loaded
(512-long-side) frames the solver actually worked on:

  * epipolar — symmetric point-to-epipolar-line distance, from poses + focals only.
    Available for EVERY run, no re-solving. Tests whether the recovered poses explain
    the matches. Necessary but weaker: a point can sit on the epipolar line at the
    wrong depth, and the metric degenerates as the baseline goes to zero (a pure
    rotation has no epipolar geometry), so per-pair baselines are reported alongside.

  * reproj — unproject a correspondence through image i's depthmap, project into
    image j, measure the pixel miss. Needs per-pixel depth, which lives in dense.npz,
    so only runs invoked with --dense have it. This is the structure metric: it tests
    depth and pose together and does not degenerate at short baseline.

Both are computed PER PAIR, which is the point: a single false link (the Doppelganger
hazard) shows up as one pair disagreeing with an otherwise coherent solve, which a
run-level scalar would average away.

CAVEAT ON ABSOLUTE VALUES. sparse_ga optimizes principal points (opt_pp=True), but
scene.npz did not save intrinsics until July 2026, so for older runs the pp would have to
be approximated by the image centre — and that bias is bigger than a good solve's entire
error (masktest: 0.71 px with true pps, 3.57 px with centre-pp). Never quote an absolute
number from a centre-pp run. Fix it instead: `recon_resolve.py <rundir>` re-solves from
the intact cache (deterministic; reproduces the archived poses exactly) and writes an
intrinsics.npz sidecar that this module picks up automatically. pp_source in the output
says which source was used.

    .venv/bin/python recon_metrics.py runs/walk_dense runs/walk_sparse
    .venv/bin/python recon_metrics.py --self-test
"""
import argparse
import glob
import hashlib
import json
import math
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# Correspondences below this confidence are dropped. The solver used
# matching_conf_thr=5.0 to decide whether a PAIR was usable at all; per-correspondence
# conf spans ~0.1-5, so a threshold here is a different knob. 0 = keep everything.
CONF_THR = 0.0

# A pair whose baseline is under this fraction of the median scene depth has no usable
# epipolar geometry (E = [t]x R degenerates as t -> 0). Reported, not silently dropped.
DEGENERATE_BASELINE_FRAC = 0.01


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def hash_md5(s):
    """Same keying MASt3R's cache uses (mast3r.utils.misc.hash_md5) — reimplemented so
    this module needs neither mast3r on sys.path nor a model import."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _load_pth(path):
    import torch
    return torch.load(path, map_location="cpu", weights_only=False)


def _np(x):
    return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)


# ---------- locating a run's pieces ----------
def frame_keys(meta):
    """Cache keys for each frame, in frame order.

    The cache is keyed by hash_md5 of the image path STRING as handed to load_images at
    run time, i.e. '<args.out>/imgs/<idx>_<id8>.jpg' (download() names them at
    reconstruct.py:304). Today's absolute path hashes differently, so rebuild the
    original relative string rather than guessing from the filesystem.
    """
    out = meta["args"]["out"]
    return [hash_md5(os.path.join(out, "imgs", f"{f['idx']:03d}_{f['id'][:8]}.jpg"))
            for f in meta["frames"]]


def canon_paths(rundir, keys):
    """Per-frame canonical-view cache path (holds the loaded H,W and the base focal)."""
    d = os.path.join(rundir, "cache", "canon_views")
    out = []
    for k in keys:
        hit = glob.glob(os.path.join(d, f"{k}_*.pth"))
        out.append(hit[0] if hit else None)
    return out


def read_frame_geometry(paths):
    """→ (H, W, base_focal) per frame, from the canonical views.

    conf.shape is the exact loaded frame size — the size every cached correspondence
    coordinate and every depthmap index is expressed in.
    """
    H, W, bf = [], [], []
    for p in paths:
        if p is None:
            H.append(0); W.append(0); bf.append(np.nan)
            continue
        (_canon, _canon2, conf), focal = _load_pth(p)
        h, w = tuple(conf.shape)
        H.append(int(h)); W.append(int(w)); bf.append(float(_np(focal).ravel()[0]))
    return np.array(H), np.array(W), np.array(bf)


def read_corres(rundir, keys, conf_thr=CONF_THR):
    """→ {(i, j): (xy1, xy2, confs)} over every cached ordered pair.

    Payload is ((score, conf_sum, n), (xy1, xy2, confs)) with xy as int64 (col, row) in
    the loaded frame — the format install_corr_masking rewrites (reconstruct.py:285).
    """
    idx = {k: i for i, k in enumerate(keys)}
    dirs = glob.glob(os.path.join(rundir, "cache", "corres_conf=*"))
    out, skipped = {}, 0
    for d in dirs:
        for f in glob.glob(os.path.join(d, "*.pth")):
            name = os.path.splitext(os.path.basename(f))[0]
            if "-" not in name:
                continue
            h1, h2 = name.split("-", 1)
            if h1 not in idx or h2 not in idx:
                skipped += 1
                continue
            try:
                _score, (xy1, xy2, confs) = _load_pth(f)
            except Exception:
                skipped += 1
                continue
            xy1, xy2, confs = _np(xy1), _np(xy2), _np(confs).ravel()
            if conf_thr > 0:
                keep = confs >= conf_thr
                xy1, xy2, confs = xy1[keep], xy2[keep], confs[keep]
            out[(idx[h1], idx[h2])] = (xy1.astype(np.float64),
                                       xy2.astype(np.float64), confs)
    if skipped:
        log(f"  note: {skipped} corres file(s) unresolved/unreadable")
    return out


def read_intrinsics_sidecar(rundir, name="intrinsics.npz"):
    """The exact intrinsics recovered by recon_resolve.py, or None.

    scene.npz predates saving principal points, so this sidecar is how an archived run
    gets its true pps (and, for runs solved without --dense, its depthmaps).
    """
    p = os.path.join(rundir, name)
    if not os.path.exists(p):
        return None
    z = np.load(p, allow_pickle=True)
    out = {"K": z["K"].astype(np.float64),
           "poses": z["poses"].astype(np.float64),
           "focals": z["focals"].astype(np.float64).ravel(),
           "faithful": bool(z["faithful"]) if "faithful" in z.files else True,
           # this solve's units -> the archived solve's units (see recon_resolve)
           "scale_to_archived": (float(z["scale_to_archived"])
                                 if "scale_to_archived" in z.files else 1.0)}
    if "depthmaps" in z.files:
        out["depthmaps"] = z["depthmaps"]
    return out


def umeyama(src, dst):
    """Similarity transform (s, R, t) mapping src -> dst (Nx3). Same fit reconstruct.py
    uses for its GPS residual, duplicated here so this module stays importable without
    dragging in reconstruct.py's argparse/torch-heavy main."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    S, D = src - mu_s, dst - mu_d
    C = D.T @ S / len(src)
    U, sig, Vt = np.linalg.svd(C)
    F = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        F[2, 2] = -1
    R = U @ F @ Vt
    var = (S ** 2).sum() / len(src)
    s = float(np.trace(np.diag(sig) @ F) / var) if var else 1.0
    return s, R, mu_d - s * (R @ mu_s)


def gps_residuals(meta, poses):
    """Horizontal camera<->GPS residual (m) for the poses we are actually scoring.

    metadata.json's residuals belong to the archived solve. When a re-solve lands in a
    different local minimum (it happens on the bigger runs) its structure metrics must be
    compared against ITS own drift, not the archived run's — otherwise the two numbers
    describe different reconstructions.
    """
    frames = meta["frames"]
    lat0, lon0 = meta["center"]
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    alts = [f.get("altitude") for f in frames]
    known = [a for a in alts if a is not None]
    alt0 = float(np.mean(known)) if known else 0.0
    enu, real, ok = [], [], []
    for f, a in zip(frames, alts):
        g = f.get("gps")
        ok.append(g is not None)
        enu.append([(g[1] - lon0) * kx, (g[0] - lat0) * ky,
                    (a - alt0) if a is not None else 0.0] if g else [0.0, 0.0, 0.0])
        real.append(not f.get("injected"))
    enu, real, ok = np.array(enu), np.array(real), np.array(ok)
    cams = poses[:, :3, 3]
    fit = real & ok
    if fit.sum() < 3:
        return None
    s, R, t = umeyama(cams[fit], enu[fit])
    rec = (s * (R @ cams.T)).T + t
    resid = np.linalg.norm(rec[:, :2] - enu[:, :2], axis=1)
    rr = resid[real & ok]
    return {"med_resid": round(float(np.median(rr)), 3),
            "mean_resid": round(float(rr.mean()), 3),
            "max_resid": round(float(rr.max()), 3),
            "scale_units_per_m": round(float(s), 6),
            "per_frame": [round(float(v), 3) if o else None for v, o in zip(resid, ok)]}


def _coerce_depth(raw, n_frames, HW, where):
    out = []
    for i in range(n_frames):
        row = raw[i] if i < len(raw) else None
        d = None if row is None else np.asarray(row, dtype=np.float32).ravel()
        h, w = HW[i]
        if d is not None and d.size != h * w:
            log(f"  frame {i}: {where} depthmap size {d.size} != {h}x{w}, ignoring")
            d = None
        out.append(d)
    return out


def sidecar_depthmaps(side, n_frames, HW):
    return _coerce_depth(side["depthmaps"], n_frames, HW, "sidecar")


def read_depthmaps(rundir, n_frames, HW):
    """Per-frame per-pixel z-depth from dense.npz, or None when the run had no --dense.

    reconstruct.py saves these as np.array(list_of_ravelled_arrays, dtype=object)
    (:739), so the array can come back 2-D (uniform sizes) or 1-D (ragged); and its
    elements are boxed floats. Convert to float32 once and drop the object array —
    a 70-frame run is ~10M boxed floats otherwise.
    """
    p = os.path.join(rundir, "dense.npz")
    if not os.path.exists(p):
        return None
    with np.load(p, allow_pickle=True) as z:
        if "depthmaps" not in z.files:
            return None
        raw = z["depthmaps"]
    out = _coerce_depth(raw, n_frames, HW, "dense.npz")
    del raw
    return out


# ---------- geometry ----------
def intrinsics(focals, W, H, pps=None):
    """K per frame: fx=fy=focal, principal point at pps (normalized) or the image centre.

    Mirrors sparse_ga.make_K_cam_depth: K[:,0,0]=K[:,1,1]=focal and
    K[:,0:2,2] = pps * imsizes, where pps initializes to (0.5, 0.5).
    """
    n = len(focals)
    K = np.zeros((n, 3, 3))
    K[:, 0, 0] = K[:, 1, 1] = focals
    K[:, 2, 2] = 1.0
    if pps is None:
        K[:, 0, 2] = W / 2.0
        K[:, 1, 2] = H / 2.0
    else:
        pps = np.asarray(pps, float).reshape(n, 2)
        K[:, 0, 2] = pps[:, 0] * W
        K[:, 1, 2] = pps[:, 1] * H
    return K


def _skew(t):
    return np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])


def _homog(xy):
    return np.concatenate([xy, np.ones((len(xy), 1))], 1)


def epipolar_pair(Ki, Kj, cam2w_i, cam2w_j, xy1, xy2):
    """Symmetric point-to-epipolar-line distance in px, plus the pair's baseline.

    → (err, baseline) where err[k] is the mean of the two point-to-line distances for
    correspondence k (one in each image).
    """
    T = np.linalg.inv(cam2w_j) @ cam2w_i          # maps camera i coords into camera j
    R, t = T[:3, :3], T[:3, 3]
    F = np.linalg.inv(Kj).T @ (_skew(t) @ R) @ np.linalg.inv(Ki)
    x1, x2 = _homog(xy1), _homog(xy2)
    l2 = x1 @ F.T                                  # epipolar lines in image j
    l1 = x2 @ F                                    # epipolar lines in image i
    num = np.abs(np.sum(x2 * l2, axis=1))
    n2 = np.linalg.norm(l2[:, :2], axis=1)
    n1 = np.linalg.norm(l1[:, :2], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        err = 0.5 * (num / n2 + num / n1)
    return err, float(np.linalg.norm(t))


def reproj_pair(Ki, Kj, cam2w_i, cam2w_j, depth_i, Wi, xy1, xy2):
    """Reprojection error in px: unproject xy1 via image i's depth, project into j.

    → (err, n_behind). Correspondences with no/невalid depth are dropped; ones landing
    behind camera j are counted separately rather than folded into the error.
    """
    ix = xy1[:, 1].astype(int) * Wi + xy1[:, 0].astype(int)
    ok = (ix >= 0) & (ix < depth_i.size)
    z = np.full(len(xy1), np.nan)
    z[ok] = depth_i[ix[ok]]
    good = np.isfinite(z) & (z > 0)
    if not good.any():
        return np.zeros(0), 0
    xy1g, xy2g, zg = xy1[good], xy2[good], z[good]

    # pixel + z-depth -> camera-frame point (proj3d in sparse_ga)
    Xc = np.stack([(xy1g[:, 0] - Ki[0, 2]) / Ki[0, 0] * zg,
                   (xy1g[:, 1] - Ki[1, 2]) / Ki[1, 1] * zg,
                   zg], 1)
    Xw = Xc @ cam2w_i[:3, :3].T + cam2w_i[:3, 3]
    w2c = np.linalg.inv(cam2w_j)
    Xj = Xw @ w2c[:3, :3].T + w2c[:3, 3]

    front = Xj[:, 2] > 1e-9
    n_behind = int((~front).sum())
    if not front.any():
        return np.zeros(0), n_behind
    Xj, xy2g = Xj[front], xy2g[front]
    u = Kj[0, 0] * Xj[:, 0] / Xj[:, 2] + Kj[0, 2]
    v = Kj[1, 1] * Xj[:, 1] / Xj[:, 2] + Kj[1, 2]
    return np.hypot(u - xy2g[:, 0], v - xy2g[:, 1]), n_behind


# ---------- run-level driver ----------
def gps_extent(meta, injected):
    """Widest distance between two real frames' GPS positions, in metres."""
    frames = meta["frames"]
    lat0, lon0 = meta["center"]
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110540.0
    pts = [((f["gps"][1] - lon0) * kx, (f["gps"][0] - lat0) * ky)
           for f, inj in zip(frames, injected) if f.get("gps") and not inj]
    if len(pts) < 2:
        return None
    P = np.array(pts)
    d = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=-1)
    return float(d.max())


def depth_horizon(poses, focals, injected, depth, upm, meta=None):
    """How far this cluster's own geometry can constrain depth, and how much of the depth it
    reports lies beyond that.

    Triangulated depth error grows as z²/(f·B): one pixel of disparity error costs
    dz/z = z/(f·B). So a cluster has an honest horizon, and past it the solver is reporting
    its monocular prior rather than measured geometry. This exists because a whole
    experiment was over-read for want of it — a lookout pan with a 1.47 m baseline
    "reconstructed" a vista of kilometre-distant landmarks entirely inside 62 m, and the
    20%-error horizon for that baseline is 114 m. Standing still to photograph a vista is
    the same thing as having no baseline.

    Returns metres when upm is known, else scene units (flagged by `units`).
    """
    real = [i for i, v in enumerate(injected) if not v]
    if len(real) < 2:
        return None
    cams = poses[real][:, :3, 3]
    d = np.linalg.norm(cams[:, None, :] - cams[None, :, :], axis=-1)
    base = float(d.max())
    f = float(np.median(focals))
    if base <= 0 or f <= 0:
        return None
    # 20% is the point past which a single pixel of matching error dominates the answer.
    # Baseline, depth and horizon are all in SCENE units here; the conversion happens once,
    # at the end. NOTE the direction: metadata's `scale_units_per_m` is the Umeyama scale
    # mapping scene -> ENU metres, i.e. it is metres PER UNIT despite the name, so metres =
    # units * s. Dividing (the name's reading) inflated masktest's 1.2 m baseline to 24 m.
    horizon = 0.2 * f * base
    m_per_unit = upm or 1.0
    out = {"units": "m" if upm else "scene",
           "baseline_max": round(base * m_per_unit, 3),
           "horizon_20pct": round(horizon * m_per_unit, 1),
           "median_focal_px": round(f, 1)}
    vals = [d_[np.isfinite(d_) & (d_ > 0)] for d_ in (depth or []) if d_ is not None]
    if vals:
        allz = np.concatenate(vals)
        out["depth_p50"] = round(float(np.percentile(allz, 50)) * m_per_unit, 2)
        out["depth_p90"] = round(float(np.percentile(allz, 90)) * m_per_unit, 2)
        out["depth_max"] = round(float(allz.max()) * m_per_unit, 2)
        out["frac_beyond_horizon"] = round(float((allz > horizon).mean()), 4)
        # the honest reading of a solve that claims depth it cannot measure
        out["over_reported"] = bool(out["frac_beyond_horizon"] > 0.05)

    # Recovered camera spread vs the GPS spread. Umeyama fits the scale, so a faithful solve
    # lands near 1 and a badly compressed one lands low. Reported as a diagnostic, NOT sold
    # as a collapse detector: measured over the archived runs it ranks plausibly (walk_sparse
    # lowest at 0.59, walk_dense 0.98, masktest 1.04) but does NOT separate good from bad —
    # walk_jizni is a fine solve at 1.96 px and sits at 0.68, close to walk_sparse. Nothing
    # in the archive trips the threshold below. Treat a low ratio as a prompt to look, not a
    # verdict. (An earlier version of this claimed a dramatic 0.005 for walk_sparse; that was
    # a unit bug — dividing by metadata's `scale_units_per_m` instead of multiplying.)
    if meta is not None:
        g = gps_extent(meta, injected)
        if g and g > 1e-6:
            out["gps_baseline_max"] = round(g, 2)
            out["baseline_ratio"] = round(out["baseline_max"] / g, 4)
            # Umeyama fits the scale, so a healthy solve lands near 1. Well under that means
            # the recovered cloud is genuinely more compact than reality — a collapse, not
            # drift. Threshold deliberately loose: 0.5 is already a 2x scale error.
            out["collapsed"] = bool(out["baseline_ratio"] < 0.5)
    return out


def _stats(e):
    e = np.asarray(e)
    e = e[np.isfinite(e)]
    if not e.size:
        return None
    return {"n": int(e.size),
            "median": round(float(np.median(e)), 4),
            "mean": round(float(e.mean()), 4),
            "rms": round(float(np.sqrt((e ** 2).mean())), 4),
            "p90": round(float(np.percentile(e, 90)), 4),
            "max": round(float(e.max()), 4)}


def measure(rundir, conf_thr=CONF_THR, pps=None):
    """Compute both metrics for one run dir → a metrics dict (also the metrics.json body)."""
    meta = json.load(open(os.path.join(rundir, "metadata.json")))
    frames = meta["frames"]
    n = len(frames)
    keys = frame_keys(meta)
    cps = canon_paths(rundir, keys)
    missing = [i for i, p in enumerate(cps) if p is None]
    if missing:
        raise SystemExit(
            f"{rundir}: {len(missing)}/{n} frames have no canonical view in the cache "
            f"(first missing idx {missing[0]}). The cache keys are hash_md5 of the "
            f"run-time path string built from metadata args.out={meta['args']['out']!r}; "
            f"if the run dir was renamed or args.out differed, that mapping is broken.")

    H, W, base_focals = read_frame_geometry(cps)
    scene = np.load(os.path.join(rundir, "scene.npz"))
    poses = scene["poses"].astype(np.float64)
    focals = scene["focals"].astype(np.float64).ravel()

    # Principal points, best source first. They matter: on masktest the true pps sit
    # 4-6 px off centre, which alone moved the reprojection median from 0.71 to 3.57 px.
    pp_source, pose_source, K, faithful = "image-centre-approx", "scene.npz", None, True
    gauge_scale, rms_frac, rel_focal = 1.0, 0.0, 0.0
    side = read_intrinsics_sidecar(rundir)
    if pps is not None:
        pp_source = "caller"
    elif "intrinsics" in scene.files:               # runs saved after the intrinsics fix
        K, pp_source = scene["intrinsics"].astype(np.float64), "scene.npz"
    elif side is not None:
        # NEVER mix intrinsics from one solve with poses from another: on the bigger runs
        # a re-solve can settle in a different local minimum (walk_dense moved 129% of the
        # scene extent), and pairing its K with the archived poses would manufacture error
        # that belongs to neither solve. Take the sidecar's poses too, and say so.
        K, pp_source = side["K"], "recon_resolve sidecar"
        archived_cams = poses[:, :3, 3].copy()
        poses, focals = side["poses"], side["focals"]
        pose_source = "recon_resolve sidecar"
        # Compare the two solves ourselves rather than trusting the sidecar's stored flag:
        # a reconstruction is only defined up to a global similarity, so align first. The
        # scale that alignment recovers is also what reconciles the archived depthmaps
        # with these poses.
        gauge_scale, _R, _t = umeyama(poses[:, :3, 3], archived_cams)
        aligned = (gauge_scale * (_R @ poses[:, :3, 3].T)).T + _t
        extent = float(np.ptp(archived_cams, axis=0).max()) or 1.0
        rms_frac = float(np.sqrt(((aligned - archived_cams) ** 2).sum(1).mean())) / extent
        rel_focal = float(np.abs((scene["focals"].astype(np.float64).ravel() - focals)
                                 / np.maximum(scene["focals"].astype(np.float64).ravel(),
                                              1e-9)).max())
        faithful = rms_frac < 0.02 and rel_focal < 0.05
        log(f"  re-solve vs archived (gauge-aligned): camera RMS "
            f"{100 * rms_frac:.3g}% of extent, scale {gauge_scale:.5f}, "
            f"focals within {100 * rel_focal:.2f}%"
            f"{'' if faithful else '  <-- genuinely a different reconstruction'}")
    if K is None:
        K = intrinsics(focals, W, H, pps)

    corres = read_corres(rundir, keys, conf_thr)
    depth_source = "dense.npz"
    depth = read_depthmaps(rundir, n, list(zip(H, W)))
    if depth is None and side is not None and "depthmaps" in side:
        depth, depth_source = sidecar_depthmaps(side, n, list(zip(H, W))), "sidecar"
    elif depth is not None and pose_source.startswith("recon_resolve"):
        # dense.npz depth is in the ARCHIVED gauge while these poses are in the re-solve's.
        # A reconstruction is only defined up to a global similarity, so the depths must be
        # converted or the baseline and the depth disagree by that scale factor.
        if abs(gauge_scale - 1.0) > 1e-9:
            depth = [None if d is None else (d / gauge_scale).astype(np.float32)
                     for d in depth]
            depth_source = f"dense.npz rescaled by 1/{gauge_scale:.5f}"
    log(f"{os.path.basename(rundir)}: {n} frames, {len(corres)} cached pairs, "
        f"depth={'yes' if depth else 'no'}, pp={pp_source}")

    # Drift for the poses we are actually scoring (see gps_residuals). Falls back to the
    # archived numbers if the GPS is too sparse to fit.
    gps_own = gps_residuals(meta, poses)
    upm = (gps_own or {}).get("scale_units_per_m") \
        or (meta.get("alignment") or {}).get("scale_units_per_m") or None
    cams = poses[:, :3, 3]
    med_depth = float(np.median(np.linalg.norm(cams - cams.mean(0), axis=1))) or 1.0

    # Injected impostors (--inject / manifest "injected"): the Doppelganger control. They
    # are excluded from the GPS alignment fit upstream so they cannot drag the similarity
    # toward themselves, and here they are scored SEPARATELY — the thesis is that a frame
    # which fools pairwise matching cannot register into a globally consistent solve, and
    # that claim is only testable if the impostor's error is compared against the real
    # frames' own baseline rather than averaged into it.
    injected = [bool(f.get("injected")) for f in frames]

    pairs, ep_all, rp_all, n_corres_total = [], [], [], 0
    # real-real pairs only, so the baseline the impostor is judged against is clean
    ep_real, rp_real = [], []
    imp_ep = {i: [] for i, v in enumerate(injected) if v}
    imp_rp = {i: [] for i, v in enumerate(injected) if v}
    imp_corres = {i: 0 for i, v in enumerate(injected) if v}
    per_frame_ep = [[] for _ in range(n)]
    per_frame_rp = [[] for _ in range(n)]
    for (i, j), (xy1, xy2, confs) in sorted(corres.items()):
        n_corres_total += len(xy1)
        ep, base = epipolar_pair(K[i], K[j], poses[i], poses[j], xy1, xy2)
        rec = {"i": i, "j": j, "n_corres": int(len(xy1)),
               "baseline_units": round(base, 4)}
        if upm:
            rec["baseline_m"] = round(base / upm, 2)
        rec["degenerate_baseline"] = bool(base < DEGENERATE_BASELINE_FRAC * med_depth)
        touches_imp = injected[i] or injected[j]
        if touches_imp:
            rec["impostor_pair"] = True
            for k in (i, j):
                if injected[k]:
                    imp_corres[k] += int(len(xy1))
        s = _stats(ep)
        if s:
            rec["epipolar"] = s
            if not rec["degenerate_baseline"]:
                ep_all.append(ep)
                per_frame_ep[i].append(ep); per_frame_ep[j].append(ep)
                if touches_imp:
                    for k in (i, j):
                        if injected[k]:
                            imp_ep[k].append(ep)
                else:
                    ep_real.append(ep)
        if depth is not None and depth[i] is not None:
            rp, n_behind = reproj_pair(K[i], K[j], poses[i], poses[j],
                                       depth[i], int(W[i]), xy1, xy2)
            s = _stats(rp)
            if s:
                rec["reproj"] = s
                rec["n_behind_camera"] = n_behind
                rp_all.append(rp)
                per_frame_rp[i].append(rp); per_frame_rp[j].append(rp)
                if touches_imp:
                    for k in (i, j):
                        if injected[k]:
                            imp_rp[k].append(rp)
                else:
                    rp_real.append(rp)
        pairs.append(rec)

    def pooled(chunks):
        return _stats(np.concatenate(chunks)) if chunks else None

    def pooled_median(chunks):
        s = pooled(chunks)
        return s["median"] if s else None

    def per_pair_median(key):
        v = [p[key]["median"] for p in pairs
             if key in p and not (key == "epipolar" and p["degenerate_baseline"])]
        return round(float(np.median(v)), 4) if v else None

    # The Doppelganger verdict. `ratio` is the impostor's error over the real frames' own
    # baseline: >> 1 means global consistency rejected it, ~1 means it registered as well
    # as a genuine frame and the thesis failed for this case. n_corres matters just as
    # much: an impostor that simply produced no matches was never a test of anything, so
    # it is reported rather than allowed to masquerade as a pass.
    impostors = []
    real_rp, real_ep = pooled(rp_real), pooled(ep_real)
    for i, is_imp in enumerate(injected):
        if not is_imp:
            continue
        i_rp, i_ep = pooled(imp_rp.get(i) or []), pooled(imp_ep.get(i) or [])
        rec = {
            "idx": frames[i]["idx"], "id": frames[i].get("id"),
            "n_corres_to_cluster": imp_corres.get(i, 0),
            "reproj_px": i_rp, "epipolar_px": i_ep,
            "gps_residual_m": ((gps_own or {}).get("per_frame") or [None] * n)[i],
        }
        for key, imp, base in (("reproj", i_rp, real_rp), ("epipolar", i_ep, real_ep)):
            if imp and base and base["median"]:
                rec[f"{key}_ratio_vs_real"] = round(imp["median"] / base["median"], 2)
        rec["verdict"] = (
            "no-matches" if rec["n_corres_to_cluster"] < 100 else
            "rejected" if (rec.get("reproj_ratio_vs_real") or
                           rec.get("epipolar_ratio_vs_real") or 0) >= 5 else
            "registered" if (rec.get("reproj_ratio_vs_real") or
                             rec.get("epipolar_ratio_vs_real") or 99) <= 2 else
            "ambiguous")
        impostors.append(rec)

    out = {
        "run": os.path.basename(os.path.abspath(rundir)),
        "n_frames": n,
        "n_pairs": len(pairs),
        "n_injected": sum(injected),
        "depth_horizon": depth_horizon(poses, focals, injected, depth, upm, meta),
        # baseline over real-real pairs only — what an impostor is compared against
        "real_only_reproj_px": real_rp if any(injected) else None,
        "real_only_epipolar_px": real_ep if any(injected) else None,
        "impostors": impostors,
        "conf_thr": conf_thr,
        "pp_source": pp_source,
        "loaded_size": {"h": int(H[0]), "w": int(W[0])} if n else None,
        "scale_units_per_m": upm,
        "epipolar_px": pooled(ep_all),
        "reproj_px": pooled(rp_all),
        # What fraction of correspondences the reprojection metric could actually score.
        # Pixels whose depth was cleaned away (clean_depth) or that land behind the other
        # camera are dropped, so a low coverage means the reproj number describes a
        # subset — and a solve bad enough to push points behind cameras will LOOK better
        # than it is, because those correspondences are excluded rather than penalized.
        # Denominator is EVERY cached correspondence, not just the epipolar-scored ones:
        # zero-baseline pairs are excluded from epipolar but still reprojected, which
        # otherwise pushes coverage above 100%.
        "reproj_coverage": (round(sum(len(c) for c in rp_all) / max(n_corres_total, 1), 4)
                            if rp_all else None),
        "n_behind_camera": int(sum(p.get("n_behind_camera", 0) for p in pairs)),
        "epipolar_px_median_of_pairs": per_pair_median("epipolar"),
        "reproj_px_median_of_pairs": per_pair_median("reproj"),
        "n_degenerate_baseline_pairs": int(sum(p["degenerate_baseline"] for p in pairs)),
        "pose_source": pose_source,
        "depth_source": depth_source,
        "reproduced_archived_solve": faithful,
        "resolve_vs_archived": {"aligned_camera_rms_frac_extent": round(rms_frac, 6),
                                "gauge_scale": round(gauge_scale, 6),
                                "max_rel_focal_delta": round(rel_focal, 6)},
        # The drift gate for the SCORED poses, so both numbers describe one solve.
        "gps_residual_m": ({k: gps_own[k] for k in ("med_resid", "mean_resid", "max_resid")}
                           if gps_own else
                           {k: meta["stats"].get(k) for k in
                            ("med_resid", "mean_resid", "max_resid")}),
        "gps_residual_archived_m": {k: meta["stats"].get(k) for k in
                                    ("med_resid", "mean_resid", "max_resid")},
        # A 7-DoF Umeyama fit over 3 cameras has 9 observations for 7 parameters, so its
        # residual is very nearly arithmetic — board_jan reports 0.0 m while being the
        # worst-structured run on disk. Below this many cameras the GPS number carries
        # no information and must not be read as quality OR as drift.
        "gps_residual_informative": bool(n >= 5),
        "frames": [{"idx": frames[i]["idx"], "id": frames[i]["id"],
                    "focal_px": round(float(focals[i]), 2),
                    "base_focal_px": round(float(base_focals[i]), 2),
                    "injected": injected[i],
                    "residual_m": ((gps_own or {}).get("per_frame") or
                                   [f.get("residual_m") for f in frames])[i],
                    "epipolar_px": pooled_median(per_frame_ep[i]),
                    "reproj_px": pooled_median(per_frame_rp[i])}
                   for i in range(n)],
        "pairs": pairs,
    }
    # the worst pairs are the whole point: a false link hides in the tail, not the mean
    key = "reproj" if rp_all else "epipolar"
    ranked = sorted((p for p in pairs if key in p),
                    key=lambda p: -p[key]["median"])
    out["worst_pairs"] = [{"i": p["i"], "j": p["j"], "metric": key,
                           "median_px": p[key]["median"],
                           "n_corres": p["n_corres"]} for p in ranked[:10]]
    return out


def print_summary(m):
    ep, rp = m["epipolar_px"], m["reproj_px"]
    log(f"  epipolar: {'median %.2f px  rms %.2f  p90 %.2f  (n=%d)' % (ep['median'], ep['rms'], ep['p90'], ep['n']) if ep else 'n/a'}")
    log(f"  reproj:   {'median %.2f px  rms %.2f  p90 %.2f  (n=%d)' % (rp['median'], rp['rms'], rp['p90'], rp['n']) if rp else 'n/a (run had no --dense)'}")
    if m.get("reproj_coverage") is not None:
        log(f"  reproj coverage: {100 * m['reproj_coverage']:.1f}% of correspondences "
            f"({m['n_behind_camera']} landed behind a camera)")
    log(f"  GPS residual (drift gate): med {m['gps_residual_m']['med_resid']:.1f} m")
    if m["n_degenerate_baseline_pairs"]:
        log(f"  {m['n_degenerate_baseline_pairs']} pair(s) excluded from epipolar: baseline ~ 0")
    for p in m["worst_pairs"][:3]:
        log(f"  worst {p['metric']}: pair {p['i']}->{p['j']} "
            f"{p['median_px']:.2f} px over {p['n_corres']} corres")
    dh = m.get("depth_horizon")
    if dh:
        u = dh["units"]
        log(f"  depth horizon: baseline {dh['baseline_max']} {u} → honest to "
            f"~{dh['horizon_20pct']} {u} (20% error); this solve reports depth to "
            f"{dh.get('depth_max')} {u}")
        if dh.get("baseline_ratio") is not None:
            log(f"    recovered spread is {dh['baseline_ratio']:.2f}x the GPS spread "
                f"({dh['gps_baseline_max']} m)"
                + ("  <-- heavily compressed, worth a look"
                   if dh.get("collapsed") else ""))
        if dh.get("over_reported"):
            log(f"    WARNING: {100 * dh['frac_beyond_horizon']:.1f}% of depth is beyond "
                f"what this baseline can constrain — that part is the monocular prior, "
                f"not measured geometry")
        else:
            # The other failure, which no internal check can see: the horizon itself may be
            # far short of the subject. A lookout pan stays honestly inside 114 m while
            # photographing landmarks kilometres away.
            log(f"    (compare {dh['horizon_20pct']} {u} against how far away your SUBJECT "
                f"is — a solve can be internally honest and still miss the scene entirely)")
    if m.get("impostors"):
        base = m.get("real_only_reproj_px") or m.get("real_only_epipolar_px")
        log(f"  IMPOSTOR CONTROL — real frames alone: "
            f"reproj {(m.get('real_only_reproj_px') or {}).get('median', float('nan')):.2f} px, "
            f"epipolar {(m.get('real_only_epipolar_px') or {}).get('median', float('nan')):.2f} px"
            f"{'' if base else ' (no baseline)'}")
        for imp in m["impostors"]:
            rp = (imp.get("reproj_px") or {}).get("median")
            ep = (imp.get("epipolar_px") or {}).get("median")
            log(f"    frame {imp['idx']} {str(imp.get('id'))[:8]}: {imp['verdict'].upper()} "
                f"— reproj {rp if rp is None else round(rp, 2)} px "
                f"(x{imp.get('reproj_ratio_vs_real', '?')} vs real), "
                f"epipolar {ep if ep is None else round(ep, 2)} px "
                f"(x{imp.get('epipolar_ratio_vs_real', '?')}), "
                f"{imp['n_corres_to_cluster']} corres to the cluster")


# ---------- self-test ----------
def self_test():
    """Synthetic two-view scene: exact correspondences must score ~0, and a known pose
    perturbation must move both metrics by the predicted amount.

    This is the check that the metric measures what it claims — without it, a small
    number on a real run is not evidence of anything.
    """
    rng = np.random.default_rng(0)
    f, W, H = 400.0, 288, 512
    K = intrinsics(np.array([f, f]), np.array([W, W]), np.array([H, H]))

    # camera i at origin looking down +z; camera j translated along x (real baseline)
    ci = np.eye(4)
    cj = np.eye(4); cj[0, 3] = 2.0
    pts = np.stack([rng.uniform(-3, 3, 400), rng.uniform(-3, 3, 400),
                    rng.uniform(8, 20, 400)], 1)

    def project(cam2w, X):
        w2c = np.linalg.inv(cam2w)
        Xc = X @ w2c[:3, :3].T + w2c[:3, 3]
        return np.stack([f * Xc[:, 0] / Xc[:, 2] + W / 2,
                         f * Xc[:, 1] / Xc[:, 2] + H / 2], 1), Xc[:, 2]

    xy1, z1 = project(ci, pts)
    xy2, _ = project(cj, pts)
    inside = ((xy1 > 0).all(1) & (xy1 < [W, H]).all(1)
              & (xy2 > 0).all(1) & (xy2 < [W, H]).all(1))
    xy1, xy2, z1, pts = xy1[inside], xy2[inside], z1[inside], pts[inside]
    assert len(xy1) > 50, f"degenerate test scene ({len(xy1)} pts)"

    # a depthmap holding the exact z at each correspondence's (rounded) pixel
    depth = np.zeros(H * W, np.float32)
    ix = np.round(xy1[:, 1]).astype(int) * W + np.round(xy1[:, 0]).astype(int)
    depth[ix] = z1
    xy1r = np.stack([np.round(xy1[:, 0]), np.round(xy1[:, 1])], 1)

    ep, base = epipolar_pair(K[0], K[1], ci, cj, xy1, xy2)
    rp, behind = reproj_pair(K[0], K[1], ci, cj, depth, W, xy1r, xy2)
    print(f"  exact scene:  epipolar median {np.median(ep):.4f} px  "
          f"reproj median {np.median(rp):.4f} px  baseline {base:.2f}  behind {behind}")
    assert np.median(ep) < 1e-6, f"epipolar should vanish on exact data, got {np.median(ep)}"
    # reproj uses pixel-rounded lookups, so sub-pixel residue is expected
    assert np.median(rp) < 1.0, f"reproj should be sub-pixel on exact data, got {np.median(rp)}"

    # Perturb camera j's rotation by theta and check both metrics respond as predicted:
    # a small rotation shifts image content by ~f*theta px.
    #
    # The axis matters, and this is the sharpest statement of why reproj is the real
    # metric. The baseline here is along x, so epipolar lines run horizontally; a
    # rotation about Y slides points ALONG their own epipolar lines and the epipolar
    # constraint cannot see it at all (~0.1 px for a 2 deg error worth 14 px of actual
    # reprojection error). A rotation about X moves points ACROSS the lines and is
    # caught. So epipolar is a cheap screen with a blind direction, not a quality score.
    for axis in ("y", "x"):
        print(f"  --- rotation about {axis} "
              f"({'along' if axis == 'y' else 'across'} the epipolar lines) ---")
        for theta_deg in (0.1, 0.5, 2.0):
            th = np.radians(theta_deg)
            c, s = np.cos(th), np.sin(th)
            R = (np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) if axis == "y"
                 else np.array([[1, 0, 0], [0, c, -s], [0, s, c]]))
            cj_bad = cj.copy(); cj_bad[:3, :3] = R @ cj[:3, :3]
            ep_b, _ = epipolar_pair(K[0], K[1], ci, cj_bad, xy1, xy2)
            rp_b, _ = reproj_pair(K[0], K[1], ci, cj_bad, depth, W, xy1r, xy2)
            pred = f * th
            print(f"    rot {theta_deg:>4}deg: epipolar {np.median(ep_b):7.2f} px   "
                  f"reproj {np.median(rp_b):7.2f} px   (f*theta = {pred:.2f} px)")
            # reproj must track the prediction whichever axis moved
            assert np.median(rp_b) > 0.3 * pred, "reproj insensitive to a real pose error"
            assert np.median(rp_b) < 3.0 * pred, "reproj wildly overshoots the prediction"
            if axis == "x" and theta_deg >= 0.5:
                assert np.median(ep_b) > 0.3 * pred, \
                    "epipolar should see a rotation across the epipolar lines"
            if axis == "y" and theta_deg >= 2.0:
                assert np.median(ep_b) < 0.1 * pred, \
                    "expected epipolar to be blind along the epipolar lines"

    # a pure-rotation pair must be flagged degenerate rather than silently scored
    _, base0 = epipolar_pair(K[0], K[1], ci, ci, xy1, xy1)
    assert base0 == 0.0, "zero-baseline pair should report a zero baseline"
    print("  zero-baseline pair reports baseline 0 (flagged, not scored)")
    print("SELF-TEST PASSED")


def compare(rundirs, name="metrics.json"):
    """Print a cross-run table from already-computed metrics.json files.

    The columns are deliberately side by side: the whole point of these metrics is that
    they disagree with the GPS residual, so seeing both at once is the reading.
    """
    rows = []
    for d in rundirs:
        p = os.path.join(d.rstrip("/"), name)
        if not os.path.exists(p):
            log(f"  (no {name} in {d} — run without --compare first)")
            continue
        rows.append(json.load(open(p)))
    if not rows:
        return
    rows.sort(key=lambda m: (m["reproj_px"] or {}).get("median") or float("inf"))
    print(f"\n{'run':<20} {'frames':>6} {'pairs':>6} {'reproj px':>18} "
          f"{'epipolar px':>18} {'GPS resid m':>11}  pp")
    print(f"{'':<20} {'':>6} {'':>6} {'med / p90':>18} {'med / p90':>18} "
          f"{'median':>11}")
    print("-" * 96)
    for m in rows:
        rp, ep = m["reproj_px"], m["epipolar_px"]
        rps = f"{rp['median']:7.2f} /{rp['p90']:8.1f}" if rp else f"{'n/a':>16}"
        eps = f"{ep['median']:7.2f} /{ep['p90']:8.1f}" if ep else f"{'n/a':>16}"
        gps = (m["gps_residual_m"] or {}).get("med_resid")
        if m.get("gps_residual_informative") is False:
            gps_s = f"{gps:>10.1f}*"          # too few cameras to mean anything
        else:
            gps_s = f"{gps:>11.1f}"
        pp = {"scene.npz": "saved", "recon_resolve sidecar": "recovered",
              "image-centre-approx": "APPROX!"}.get(m["pp_source"], m["pp_source"])
        print(f"{m['run']:<20} {m['n_frames']:>6} {m['n_pairs']:>6} {rps:>18} "
              f"{eps:>18} {gps_s}  {pp}")
    print("\n* fewer than 5 cameras: a 7-DoF fit has almost as many parameters as "
          "observations, so the\n  GPS residual there is arithmetic, not evidence.")
    print("reproj = unproject through depth, reproject into the other view (the "
          "structure metric).\nepipolar = distance to the epipolar line; blind to error "
          "ALONG the lines, so a low\n  epipolar with a high reproj is possible and means "
          "the depth is wrong, not the poses.\nGPS residual is a drift gate only — it is "
          "here to be disagreed with.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rundirs", nargs="*", help="run directories (containing metadata.json)")
    ap.add_argument("--compare", action="store_true",
                    help="read existing metrics.json files and print a cross-run table")
    ap.add_argument("--conf_thr", type=float, default=CONF_THR,
                    help="drop correspondences below this confidence")
    ap.add_argument("--out", default="metrics.json",
                    help="filename written inside each run dir ('-' to skip writing)")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="validate the metrics on a synthetic scene and exit")
    a = ap.parse_args()

    if a.self_test:
        self_test()
        return
    if not a.rundirs:
        ap.error("give at least one run dir, or --self-test")
    if a.compare:
        compare(a.rundirs, name=a.out if a.out != "-" else "metrics.json")
        return

    for d in a.rundirs:
        d = d.rstrip("/")
        m = measure(d, conf_thr=a.conf_thr)
        print_summary(m)
        if a.out != "-":
            p = os.path.join(d, a.out)
            with open(p, "w") as fh:
                json.dump(m, fh, indent=1)
            log(f"  wrote {p}")


if __name__ == "__main__":
    main()
