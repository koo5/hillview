#!/usr/bin/env python3
"""Bridge to the `pics` project's Mask2Former-Mapillary segmentation.

WHY NOT OUR OWN. This started as a colour heuristic — green-dominant pixels — because it
was the one cheap image statistic that predicted solve quality (3.1 px median reprojection
in the least-vegetated quartile against 42.6 in the most). It works, badly. Checked against
frames, it catches the sunlit rim of a hedge and misses its shaded body, and it cannot see
a person, a car, or the sky at all. The sibling `pics` project already runs
`facebook/mask2former-swin-large-mapillary-vistas-semantic` with a considered contract
around it, and its `mapillary-outdoor` preset is exactly the transient set this work needs:
vegetation, water, sky, snow, sand, people, riders, every kind of vehicle, animals.

WHAT THIS ADDS. Only the parts hillview needs: an interpreter that exists (the pics
diagnostics venv points at a uv-managed CPython that is no longer on this box), a cache
keyed by image content so re-running a cluster is free, and a MASK BUDGET. Inference is
~40 s per image at 1024 px, and on a hilltop frame the preset masks 79% of the picture —
mask that and there is nothing left to match on, so the budget falls back to sky and movers
only and says it did.

Environment:
    HV_SEMANTIC_PYTHON   interpreter with torch + transformers + cv2
                         (default scripts/enrich/.venv-seg/bin/python)
    HV_PICS_ROOT         the pics checkout (default ../../../pics/0/pics from here)
    HV_SEMANTIC_CACHE    where masks are kept (default scripts/enrich/runs/semantic_cache)
    HV_SEMANTIC_RES      inference short edge (default 1024)
"""
import hashlib
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# ../../../../../pics/0/pics from scripts/enrich: hillview and pics are siblings
# under the same checkout root (…/koo5/hillview/0/hillview, …/koo5/pics/0/pics)
DEFAULT_PICS = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "..", "..", "pics", "0", "pics"))


class SemanticMaskUnavailable(RuntimeError):
    """Raised rather than silently returning nothing: a run that believes it masked and
    did not is worse than a run that refused to start."""


def _python() -> str:
    p = os.getenv("HV_SEMANTIC_PYTHON") or os.path.join(HERE, ".venv-seg", "bin", "python")
    if not os.path.exists(p):
        raise SemanticMaskUnavailable(
            f"no segmentation interpreter at {p}; create one with\n"
            f"  uv venv --python 3.12 {HERE}/.venv-seg && "
            f"uv pip install --python {HERE}/.venv-seg/bin/python "
            f"torch transformers scipy pillow opencv-python-headless")
    return p


def _cli() -> str:
    root = os.getenv("HV_PICS_ROOT") or DEFAULT_PICS
    p = os.path.join(root, "src", "tools", "semantic_mask_inference.py")
    if not os.path.exists(p):
        raise SemanticMaskUnavailable(f"no pics inference CLI at {p} (set HV_PICS_ROOT)")
    return p


def _cache_dir() -> str:
    d = os.getenv("HV_SEMANTIC_CACHE") or os.path.join(HERE, "runs", "semantic_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _key(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_masks(paths, log=print, infer_res=None):
    """→ {path: stem_prefix}. Runs inference for whatever is not already cached."""
    cache = _cache_dir()
    keys = {p: _key(p) for p in paths}
    todo = [p for p in paths if not os.path.exists(os.path.join(cache, keys[p] + ".mask.png"))]
    if todo:
        res = str(infer_res or os.getenv("HV_SEMANTIC_RES") or 1024)
        log(f"semantic masks: {len(todo)} to infer at {res}px "
            f"({len(paths) - len(todo)} cached) — about {40 * len(todo) // 60} min")
        args = [f"{p}={os.path.join(cache, keys[p])}" for p in todo]
        cmd = [_python(), _cli(), "--infer-res", res,
               "--classes-preset", "mapillary-outdoor", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SemanticMaskUnavailable(
                f"inference exited {proc.returncode}: {proc.stderr[-800:]}")
        bad = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("status") != "ok":
                bad.append((d.get("input"), d.get("error")))
        if bad:
            raise SemanticMaskUnavailable(f"{len(bad)} image(s) failed: {bad[:3]}")
    return {p: os.path.join(cache, keys[p]) for p in paths}


def load_mask(stem, shape, budget=0.65, log=print, name=""):
    """One boolean mask at (H, W), honouring the mask budget.

    `mask.png` is everything in the preset; `sky.png` is its sky part. When the full mask
    would cover more than `budget` of the frame, drop back to sky-only — a frame that is
    four-fifths hedge still has a fifth worth matching on, and blanking it entirely just
    removes the frame from the solve without saying so.
    """
    from PIL import Image
    H, W = shape

    def read(suffix):
        p = f"{stem}{suffix}"
        if not os.path.exists(p):
            return np.zeros((H, W), bool)
        return np.asarray(Image.open(p).convert("L").resize((W, H), Image.NEAREST)) > 127

    full = read(".mask.png")
    frac = float(full.mean())
    if frac <= budget:
        return full, {"masked_frac": round(frac, 4), "mode": "full"}
    sky = read(".sky.png")
    return sky, {"masked_frac": round(float(sky.mean()), 4), "mode": "sky-only",
                 "full_would_be": round(frac, 4)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--res", type=int)
    a = ap.parse_args()
    stems = ensure_masks(a.images, infer_res=a.res)
    from PIL import Image
    for p, stem in stems.items():
        w, h = Image.open(p).size
        m, info = load_mask(stem, (h, w))
        print(f"{os.path.basename(p)}  {info}")


if __name__ == "__main__":
    main()
