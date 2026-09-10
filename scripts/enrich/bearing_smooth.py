#!/usr/bin/env python3
"""Optional smoothing of a photo series' bearings, as named strategies you can swap.

WHY THIS IS A STRATEGY AND NOT A FIX. The bearing a photo carries is the capture app's best
guess at where the camera pointed, and it is the only one we have. But it arrives before
systematic error (a compass has hard iron, a movement-derived bearing inherits whatever the
track was doing) and before interference (rebar, a car, a lamp post). A series of them is
therefore noisy in ways that a single frame cannot reveal and a neighbourhood can.

Smoothing is not free: a walk that really did turn a corner will have that corner flattened,
and a strategy that helps a straight sidewalk can hurt a circling span. So this file holds
SEVERAL strategies behind one name each, none of them privileged, and `measure()` says what
each does to a real run. The caller records the name it used, so a run can be retried with a
different one and the two compared. Nothing here decides anything on its own.

WHAT "BETTER" MEANS. For every frame we have two headings: the bearing the photo carries, and
the heading the solve recovered for that camera. Their difference is a per-frame offset, and
across a span those offsets should be CONSTANT — one bias, whatever its cause. So the measure
is the circular concentration of the offsets: 1.0 means every frame agrees about the bias,
0 means they are scattered uniformly and no bias can be read at all. A smoothing strategy
earns its place by raising it.

Usage:
    python bearing_smooth.py <run_dir> [run_dir...]      # what each strategy does to each run
    from bearing_smooth import smooth, STRATEGIES
"""
import math
import os
import sys

import numpy as np


# ---------- circular helpers ----------
def _to_vec(deg):
    r = np.radians(np.asarray(deg, float))
    return np.stack([np.cos(r), np.sin(r)], 1)


def _to_deg(v):
    return np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 360.0


def concentration(deg):
    """Circular resultant length of a set of angles: 1 = all identical, 0 = uniform."""
    d = [x for x in deg if x is not None and np.isfinite(x)]
    if len(d) < 2:
        return 0.0
    return float(np.linalg.norm(_to_vec(d).mean(0)))


def circ_mean(deg):
    m = _to_vec([x for x in deg if x is not None]).mean(0)
    return float(math.degrees(math.atan2(m[1], m[0])) % 360.0)


def circ_diff(a, b):
    """a - b wrapped to (-180, 180]."""
    return ((a - b + 180.0) % 360.0) - 180.0


# ---------- the strategies ----------
def _window_indices(n, i, k, gaps):
    """Indices within k of i that are not across a series break."""
    lo = i
    while lo > 0 and i - lo < k and not gaps[lo - 1]:
        lo -= 1
    hi = i
    while hi < n - 1 and hi - i < k and not gaps[hi]:
        hi += 1
    return range(lo, hi + 1)


def _circ_median(vals):
    """The angle minimising summed absolute circular deviation, picked among the samples.
    Robust to a single wild reading in a way the mean is not."""
    best, bestcost = None, None
    for c in vals:
        cost = sum(abs(circ_diff(v, c)) for v in vals)
        if bestcost is None or cost < bestcost:
            best, bestcost = c, cost
    return best


def s_none(deg, gaps, **kw):
    return list(deg)


def s_median(deg, gaps, k=2, **kw):
    """Circular running median over a window of ±k frames, not crossing a break."""
    n = len(deg)
    out = []
    for i in range(n):
        vals = [deg[j] for j in _window_indices(n, i, k, gaps) if deg[j] is not None]
        out.append(_circ_median(vals) if vals else deg[i])
    return out


def s_mean(deg, gaps, k=2, **kw):
    """Circular running mean over ±k frames. Smoother than the median, less robust."""
    n = len(deg)
    out = []
    for i in range(n):
        vals = [deg[j] for j in _window_indices(n, i, k, gaps) if deg[j] is not None]
        out.append(circ_mean(vals) if vals else deg[i])
    return out


def s_reject(deg, gaps, k=3, thr=40.0, **kw):
    """Leave the series alone but DROP frames that disagree with their own neighbourhood by
    more than `thr`. A lamp post throwing one reading is not something to average into its
    neighbours; it is something to not believe."""
    n = len(deg)
    med = s_median(deg, gaps, k=k)
    return [None if (deg[i] is None or med[i] is None
                     or abs(circ_diff(deg[i], med[i])) > thr) else deg[i]
            for i in range(n)]


def s_median_reject(deg, gaps, k=2, thr=40.0, **kw):
    """Reject the outliers, then median-smooth what is left."""
    return s_median(s_reject(deg, gaps, k=k + 1, thr=thr), gaps, k=k)


STRATEGIES = {
    "none": s_none,
    "median3": lambda d, g, **kw: s_median(d, g, k=1),
    "median5": lambda d, g, **kw: s_median(d, g, k=2),
    "median9": lambda d, g, **kw: s_median(d, g, k=4),
    "mean5": lambda d, g, **kw: s_mean(d, g, k=2),
    "reject40": lambda d, g, **kw: s_reject(d, g, k=3, thr=40.0),
    "median5+reject40": lambda d, g, **kw: s_median_reject(d, g, k=2, thr=40.0),
}


def smooth(bearings, name="none", gaps=None):
    """Apply a named strategy. `gaps[i]` True means i and i+1 are not neighbours in time.
    Returns a new list, with None where a strategy chose to drop a reading."""
    if name not in STRATEGIES:
        raise KeyError(f"unknown bearing strategy {name!r}; have {sorted(STRATEGIES)}")
    n = len(bearings)
    if gaps is None:
        gaps = [False] * max(n - 1, 0)
    return STRATEGIES[name](list(bearings), list(gaps))


# ---------- measuring it on a real run ----------
def gaps_from_times(times, max_gap_s=20.0):
    """True where consecutive frames are far enough apart in time to not be neighbours."""
    out = []
    for a, b in zip(times, times[1:]):
        try:
            out.append(abs(b - a) > max_gap_s)
        except TypeError:
            out.append(False)
    return out


def measure(run_dir, api=None):
    """→ {mode: {strategy: concentration}} for one solved run.

    The offsets are (bearing - recovered heading) per frame, so this is exactly the quantity
    `recon_join_spans` reads when it decides which mode a span may quote.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import recon_join_spans as J
    run = J.Run(run_dir)
    if api:
        J.fill_bearing_sources(run, api)
    if not run.to_enu:
        return {}
    R = run.to_enu[1]
    import datetime as _dt

    def ts(f):
        try:
            return _dt.datetime.strptime(f.get("captured_at", "")[:19],
                                         "%Y-%m-%d %H:%M:%S").timestamp()
        except (ValueError, TypeError):
            return None

    rec, brg, src, times = [], [], [], []
    for i, f in enumerate(run.frames):
        fwd = R @ (run.poses[i][:3, :3] @ np.array([0.0, 0.0, 1.0]))
        if abs(fwd[0]) < 1e-9 and abs(fwd[1]) < 1e-9:
            continue
        rec.append(math.degrees(math.atan2(fwd[0], fwd[1])) % 360.0)
        c = f.get("compass_angle")
        brg.append(None if c is None else float(c) % 360.0)
        src.append(f.get("bearing_source") or "(unrecorded)")
        times.append(ts(f))
    gaps = gaps_from_times(times)
    out = {}
    for mode in sorted(set(src)):
        idx = [i for i, s in enumerate(src) if s == mode and brg[i] is not None]
        if len(idx) < 4:
            continue
        sub_b = [brg[i] for i in idx]
        sub_r = [rec[i] for i in idx]
        sub_g = [gaps[i] for i in idx[:-1]] if len(idx) > 1 else []
        row = {}
        for name in STRATEGIES:
            sm = smooth(sub_b, name, sub_g)
            offs = [circ_diff(sm[k], sub_r[k]) for k in range(len(idx)) if sm[k] is not None]
            row[name] = dict(concentration=round(concentration(offs), 3), n=len(offs))
        out[mode] = row
    return out


def main():
    api = os.getenv("RECON_API", "http://127.0.0.1:8070/api/recon")
    for d in sys.argv[1:]:
        print(f"== {os.path.basename(d.rstrip('/'))}")
        for mode, row in measure(d, api).items():
            base = row["none"]["concentration"]
            best = max((k for k in row), key=lambda k: row[k]["concentration"])
            print(f"   {mode[:40]:42s} n={row['none']['n']:3d}  none={base:.3f}")
            for name, r in row.items():
                if name == "none":
                    continue
                mark = "  <-- best" if name == best and r["concentration"] > base + 0.005 else ""
                print(f"      {name:18s} {r['concentration']:.3f} "
                      f"({r['concentration'] - base:+.3f}, kept {r['n']}){mark}")


if __name__ == "__main__":
    main()
