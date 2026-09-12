#!/usr/bin/env python3
"""Solver backends: the interchangeable part of a reconstruction.

WHY THIS EXISTS. Everything in a run except the solve is shared — selecting frames,
staging and tiling them, masking transients, the ENU alignment and gravity refit, the
elevation check, the ground split, the artifacts, the viewer, the joins. The solve itself
is one call, and there is now more than one model worth making it with:

  mast3r   MASt3R-SfM. Pairwise matching head -> correspondences -> sparse global
           alignment. Everything archived was produced this way, and it is the only
           backend that emits CORRESPONDENCES, which three of our four analysis tools
           read (reproj/epipolar metrics, the two-view verifier, the span joiner).

  pow3r    Pow3R + DUSt3R-style global alignment. Regresses pointmaps rather than
           matches, and takes camera intrinsics, pose and depth as optional PRIORS.
           That last part is why it matters here: its high-resolution mode is a sliding
           window whose per-window intrinsics tell the network where each crop sits,
           which is exactly the channel MASt3R does not have and the reason our own
           tiling can only assert a crop's principal point downstream, to the optimiser.

WHAT A BACKEND MUST RETURN. A Solution, in the same arrays reconstruct.py already writes,
so scene.npz / dense.npz / metadata.json keep their shape and nothing downstream changes.

WHAT IS AND IS NOT TESTED. The mast3r backend is the code that produced every archived
run, moved here unchanged. The pow3r backend is written against the real API in
naver/pow3r (AsymmetricSliding.inference_with_info, priors via add_intrinsics/add_depth/
add_relpose, pointmaps under 'pts3d'/'pts3d2' with 'conf'/'conf2') but has NOT been run
against the weights — see POW3R_UNVERIFIED below, which is deliberately loud.

Both checkpoints are non-commercial licensed (NAVER), and both are loaded with
weights_only=False, which executes what they contain. Fetch them from a route you control
and check the hash; never from a registry.
"""
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


POW3R_REPO = os.getenv("POW3R_REPO", "/opt/pow3r")
MUST3R_REPO = os.getenv("MUST3R_REPO", "/opt/must3r")


def setup_paths(backend, mast3r_repo, log=print):
    """Put the right model trees on sys.path, and ONLY those.

    Each of these repos vendors its own dust3r as a submodule, at its own commit, and they
    are not interchangeable — pow3r tracks naver/dust3r main while mast3r pins an older
    one. Having both importable means `import dust3r` resolves by sys.path order, which is
    the kind of bug that surfaces as a wrong number rather than an error. So exactly one
    family is ever on the path.
    """
    import sys
    if backend == "mast3r":
        trees = [mast3r_repo, os.path.join(mast3r_repo, "dust3r"),
                 os.path.join(mast3r_repo, "dust3r", "croco")]
    elif backend == "pow3r":
        trees = [POW3R_REPO, os.path.join(POW3R_REPO, "dust3r"),
                 os.path.join(POW3R_REPO, "dust3r", "croco")]
    else:
        raise SystemExit(f"unknown solver backend {backend!r}; have {sorted(BACKENDS)}")
    # the repo and its dust3r are required; croco is only there in some layouts, and
    # pow3r's own pow3r.tools.path_to_dust3r inserts its dust3r anyway
    for t in trees[:2]:
        if not os.path.isdir(t):
            raise SystemExit(f"solver {backend} needs {t} — is this the right image? "
                             f"(override with POW3R_REPO / MAST3R_REPO)")
    trees = [t for t in trees if os.path.isdir(t)]
    for t in trees:
        if t not in sys.path:
            sys.path.insert(0, t)
    log(f"  solver {backend}: {os.path.basename(trees[0])} + its own dust3r"
        + ("" if len(trees) > 2 else " (no croco tree; the model may not need one)"))
    return trees


@dataclass
class Solution:
    """What every backend hands back, in the arrays reconstruct.py already writes."""
    poses: np.ndarray                      # (N, 4, 4) cam2world, solve units
    focals: np.ndarray                     # (N,) pixels of the loaded frame
    intrinsics: Optional[np.ndarray]        # (N, 3, 3) or None to derive from focals
    points: np.ndarray                     # (M, 3) sparse cloud
    colors: np.ndarray                     # (M, 3)
    # dense per-frame, only when the caller asked for it
    dense_pts: Optional[list] = None        # list of (H*W, 3)
    dense_depths: Optional[list] = None     # list of (H*W,) or (H, W)
    dense_confs: Optional[list] = None      # list of (H*W,)
    # what this backend can and cannot support downstream
    emits_correspondences: bool = True
    backend: str = "mast3r"
    notes: dict = field(default_factory=dict)


POW3R_UNVERIFIED = (
    "the pow3r backend has never been run against real weights: it is written from the "
    "published API, so treat the first run as a debugging session, not a measurement"
)


# ---------------------------------------------------------------------------
def solve_mast3r(paths, pairs, cache, model, *, device, niter1, niter2,
                 shared_intrinsics, want_dense, min_conf, log=print, **kw):
    """MASt3R-SfM, exactly as every archived run was produced.

    Correspondences land in the shared cache as a side effect, which is what the
    reprojection metric, the two-view verifier and the span joiner all read.
    """
    from mast3r.cloud_opt.sparse_ga import sparse_global_alignment

    scene = sparse_global_alignment(
        paths, pairs, cache, model,
        lr1=0.07, niter1=niter1, lr2=0.01, niter2=niter2,
        device=device, matching_conf_thr=5.0,
        shared_intrinsics=shared_intrinsics)

    def tn(x):
        return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    poses = tn(scene.get_im_poses())
    focals = tn(scene.get_focals()).ravel()
    K = tn(scene.intrinsics)
    pts_l, cols_l = scene.get_sparse_pts3d(), scene.get_pts3d_colors()

    def cat(x):
        if isinstance(x, (list, tuple)):
            xs = [tn(v).reshape(-1, 3) for v in x]
            return np.concatenate(xs, 0) if xs else np.zeros((0, 3))
        return tn(x).reshape(-1, 3)

    sol = Solution(poses=poses, focals=focals, intrinsics=K,
                   points=cat(pts_l), colors=cat(cols_l),
                   emits_correspondences=True, backend="mast3r")
    if want_dense:
        d_pts, d_depths, d_confs = scene.get_dense_pts3d(clean_depth=True)
        sol.dense_pts = [tn(p).reshape(-1, 3) for p in d_pts]
        sol.dense_depths = [tn(d) for d in d_depths]
        sol.dense_confs = [tn(c).ravel() for c in d_confs]
    sol.notes["scene"] = scene          # the caller still wants scene.imgs
    return sol


# ---------------------------------------------------------------------------
def solve_pow3r(paths, pairs, cache, model, *, device, niter1, niter2,
                shared_intrinsics, want_dense, min_conf,
                exif_focals=None, hi_res=False, crop_res=(384, 512),
                log=print, **kw):
    """Pow3R pointmap regression, aligned with DUSt3R's global optimiser.

    THE POINT OF THIS BACKEND IS THE PRIORS. `exif_focals` (pixels of the loaded frame,
    which reconstruct.py already records per frame as exif_focal_px_512) becomes a K per
    view, and Pow3R conditions on it. With `hi_res`, its own AsymmetricSliding resolver
    does the crop-and-stitch internally, encoding each window's position in that window's
    intrinsics — which is the mechanism our MASt3R tiling cannot reproduce.

    NO CORRESPONDENCES COME OUT OF THIS. The reprojection and epipolar metrics, the
    two-view verifier and the span joiner all read the correspondence cache and will find
    nothing. The physical checks — ground split, elevation offset and tilt, GPS residual,
    render-and-compare — do not care, and carry the quality judgement instead.
    """
    log(f"  pow3r: {POW3R_UNVERIFIED}")
    from dust3r.cloud_opt import GlobalAlignerMode, global_aligner
    from dust3r.utils.image import load_images
    from pow3r.model import inference as P

    size = max(crop_res)
    imgs = load_images(paths, size=size, verbose=False)

    def K_for(i):
        """The intrinsics prior, BATCHED. add_intrinsics branches on K.ndim: a bare 3x3
        takes a path that unpacks true_shape as (H, W), but load_images hands out a
        batched [[H, W]], so that path raises. A (1, 3, 3) takes the per-view branch,
        which is the one that matches how the views are shaped here."""
        if not exif_focals or exif_focals[i] in (None, 0):
            return None
        h, w = (int(v) for v in imgs[i]["true_shape"][0])
        f = float(exif_focals[i])
        return np.array([[[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]]], dtype=np.float32)

    resolver = model if not hi_res else P.AsymmetricSliding(
        crop_res, bootstrap_depth="c2f_both", fix_rays="full", sparsify_depth=1.1)
    if hi_res:
        resolver.model = getattr(model, "model", model)
    resolver = resolver.to(device).eval()

    def landscape(view):
        """Pow3R's patch embed (ManyAR_PatchEmbed) asserts the BUFFER is landscape and
        reads the real orientation from true_shape, transposing portrait entries back
        itself. MASt3R's config tolerates a portrait buffer, so this never came up before —
        and a phone held upright produces nothing else. Transpose the tensor, leave
        true_shape alone, and the model sees the original image; the heads then emit their
        maps in that same original orientation, so nothing has to be undone afterwards.
        """
        import torch as _t
        v = dict(view)
        img = v["img"]
        if img.shape[-2] > img.shape[-1]:          # H > W, portrait buffer
            v["img"] = img.swapaxes(-1, -2) if isinstance(img, _t.Tensor) else img
        return v

    view1, view2, pred1, pred2 = [], [], [], []
    import torch
    n_rot = sum(1 for im in imgs if im["img"].shape[-2] > im["img"].shape[-1])
    if n_rot:
        log(f"  pow3r: {n_rot}/{len(imgs)} frames are portrait; passing them transposed, "
            f"which is what ManyAR_PatchEmbed expects")
    with torch.no_grad():
        for a_, b_ in pairs:
            ia, ib = a_["idx"], b_["idx"]
            (v1, v2), pr = resolver.inference_with_info(
                landscape(imgs[ia]), landscape(imgs[ib]),
                K1=K_for(ia), K2=K_for(ib), ret_views=True)
            # DUSt3R's aligner names the second pointmap differently from Pow3R's head
            p2 = dict(pr[1])
            if "pts3d_in_other_view" not in p2:
                p2["pts3d_in_other_view"] = p2.get("pts3d2", p2.get("pts3d"))
            if "conf" not in p2 and "conf2" in p2:
                p2["conf"] = p2["conf2"]
            view1.append(v1); view2.append(v2)
            pred1.append(dict(pr[0])); pred2.append(p2)

    out = dict(view1=_stack(view1), view2=_stack(view2),
               pred1=_stack(pred1), pred2=_stack(pred2))
    scene = global_aligner(out, device=device, mode=GlobalAlignerMode.PointCloudOptimizer)
    scene.compute_global_alignment(init="mst", niter=niter1, schedule="cosine", lr=0.01)

    def tn(x):
        return x.detach().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    poses = tn(scene.get_im_poses())
    focals = tn(scene.get_focals()).ravel()
    pts = [tn(p).reshape(-1, 3) for p in scene.get_pts3d()]
    cols = [np.asarray(im).reshape(-1, 3) for im in scene.imgs]
    conf = [tn(c).ravel() for c in scene.get_conf()]
    keep = [c > min_conf for c in conf]

    sol = Solution(
        poses=poses, focals=focals, intrinsics=tn(scene.get_intrinsics()),
        points=np.concatenate([p[k] for p, k in zip(pts, keep)]) if pts else np.zeros((0, 3)),
        colors=np.concatenate([c[k] for c, k in zip(cols, keep)]) if cols else np.zeros((0, 3)),
        emits_correspondences=False, backend="pow3r",
        notes={"scene": scene, "unverified": POW3R_UNVERIFIED,
               "hi_res": bool(hi_res), "priors": "intrinsics" if exif_focals else "none"})
    if want_dense:
        sol.dense_pts = pts
        sol.dense_depths = [tn(d) for d in scene.get_depthmaps()]
        sol.dense_confs = conf
    return sol


def _stack(dicts):
    """Per-pair dicts -> one dict of batched arrays, as the aligner expects."""
    import torch
    out = {}
    for k in dicts[0]:
        vals = [d[k] for d in dicts]
        if isinstance(vals[0], torch.Tensor):
            out[k] = torch.cat([v if v.ndim > 2 else v.unsqueeze(0) for v in vals], dim=0)
        elif isinstance(vals[0], np.ndarray):
            out[k] = np.concatenate([v[None] if v.ndim <= 2 else v for v in vals], axis=0)
        else:
            out[k] = [x for v in vals for x in (v if isinstance(v, list) else [v])]
    return out


BACKENDS = {"mast3r": solve_mast3r, "pow3r": solve_pow3r}


def load_model(backend, ckpt, device, log=print):
    """The model object a backend wants. Both are loaded with weights_only=False, so the
    provenance of the file has to be yours."""
    if backend == "mast3r":
        from mast3r.model import AsymmetricMASt3R
        return AsymmetricMASt3R.from_pretrained(ckpt).to(device).eval()
    if backend == "pow3r":
        import torch

        from pow3r.model import inference as P
        log(f"  loading Pow3R from {ckpt}")
        blob = torch.load(ckpt, map_location="cpu", weights_only=False)
        resolver = P.FakeResolver((384, 512))
        resolver.load_from_checkpoint(blob)
        return resolver.to(device).eval()
    raise SystemExit(f"unknown solver backend {backend!r}; have {sorted(BACKENDS)}")
