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


# Mapillary Vistas classes, sorted by how much a reconstruction should trust them.
#
# BUILT is the stuff that holds still and carries texture on a plane: facades, kerbs,
# poles, signs, road markings. Never masked — it is the signal.
#
# SOFT is bare ground: mud, dirt, dry grass, hillside. Static, so geometrically legitimate,
# but self-similar and texture-poor, and it is what the Prosek meadow is made of — the run
# whose neighbouring frames disagree about the ground by 75 cm. Masking it is usually
# wrong because there is nothing behind it, so it is kept and merely known about.
#
# The two TRANSIENT tiers are the ones this module removes, and they are removed in order.
# Built surface, split by what it does for GEOMETRY rather than by what it is made of.
# A facade, a fence or a pole stands up out of the scene and pins depth; a road surface
# lies in the ground plane and does not. The distinction is not pedantic: on the path
# walk of 2026-09-08 a frame measured 50% "built" and masked its hedges on that basis,
# but every one of those built pixels was Road, so what was left to match on was a single
# self-similar plane — and the reconstruction terraced into slabs at range, one per frame.
BUILT_VERTICAL = {
    "Building", "Wall", "Fence", "Bridge", "Tunnel", "Guard Rail", "Barrier",
    "Pole", "Utility Pole", "Traffic Sign (Front)", "Traffic Sign (Back)",
    "Traffic Sign Frame", "Traffic Light", "Street Light", "Banner", "Billboard",
    "Bike Rack", "Bench", "Trash Can", "Mailbox", "Fire Hydrant", "Phone Booth",
    "CCTV Camera",
}
BUILT_GROUND = {
    "Curb", "Curb Cut", "Road", "Sidewalk", "Pedestrian Area", "Service Lane",
    "Bike Lane", "Crosswalk - Plain", "Lane Marking - Crosswalk",
    "Lane Marking - General", "Manhole", "Catch Basin", "Junction Box", "Rail Track",
    "Parking",
}
BUILT = BUILT_VERTICAL | BUILT_GROUND
SOFT = {"Terrain", "Mountain", "Ground", "Pothole"}


def class_fracs(stem):
    """{class name: pixel fraction} from the cached inference record, or {}."""
    p = f"{stem}.polygons.json"
    if not os.path.exists(p):
        return {}
    try:
        with open(p) as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {c["name"]: c["frac"] for c in (d.get("stats") or {}).get("class_pixel_fracs", [])}


def load_mask(stem, shape, built_floor=0.12, log=print, name=""):
    """One boolean mask at (H, W), chosen by a LADDER rather than a single budget.

    Masking is not free: every pixel removed is a pixel the matcher cannot use, and a lot
    of this corpus is mud and hedge with nothing else in it. So the rungs are:

      always   sky, people, riders, vehicles, animals, water, snow — transient or at
               infinity, and never worth a correspondence
      then     vegetation, but ONLY if enough surface that STANDS UP remains to match on

    A frame that is a hedge and a dirt path keeps its hedge, because the alternative is a
    frame with nothing in it, and a frame with nothing in it does not fail loudly — it
    drifts, which is the failure that has cost this project the most.

    The floor is measured on BUILT_VERTICAL, not on built surface in general. A road fills
    half the frame and pins nothing: it is one plane, and its gravel is self-similar, so
    every frame is free to place it at its own depth. Measured on the path walk, gating on
    total built masked the hedges away and left exactly that, and the path came out as
    terraced slabs. A facade or a fence is what earns the right to drop the vegetation.
    """
    from PIL import Image
    H, W = shape

    def read(suffix):
        p = f"{stem}{suffix}"
        if not os.path.exists(p):
            return np.zeros((H, W), bool)
        return np.asarray(Image.open(p).convert("L").resize((W, H), Image.NEAREST)) > 127

    sky = read(".sky.png")
    rest = read(".rest.png")
    veg = read(".vegetation.png")
    movers = rest & ~veg
    base = sky | movers

    fr = class_fracs(stem)
    built = round(sum(v for k, v in fr.items() if k in BUILT), 4)
    vert = round(sum(v for k, v in fr.items() if k in BUILT_VERTICAL), 4)
    ground = round(sum(v for k, v in fr.items() if k in BUILT_GROUND), 4)
    soft = round(sum(v for k, v in fr.items() if k in SOFT), 4)
    info = {"built_frac": built, "built_vertical_frac": vert, "built_ground_frac": ground,
            "soft_frac": soft,
            "sky_frac": round(float(sky.mean()), 4),
            "mover_frac": round(float(movers.mean()), 4),
            "veg_frac": round(float(veg.mean()), 4)}
    if vert >= built_floor:
        info["rung"] = "sky+movers+vegetation"
        m = base | veg
    else:
        info["rung"] = ("sky+movers (kept vegetation: %.0f%% of the frame stands up, "
                        "%.0f%% is ground)" % (100 * vert, 100 * ground))
        m = base
    info["masked_frac"] = round(float(m.mean()), 4)
    return m, info


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
