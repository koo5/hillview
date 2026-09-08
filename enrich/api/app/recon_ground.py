"""Grounding a reconstruction: find which way is up, and fit the ENU frame around it.

WHY THIS EXISTS. `reconstruct.py` aligns a solve to the world with a 7-DoF Umeyama fit of
the camera centres against their GPS positions. For a capture that walks in a straight
line — which is most of them — the camera centres are nearly collinear, and **rotation
about the walk axis is unobservable**. The fit is then free to roll the entire world about
that axis, and it does: measured on the bench, `walk_dense` came out rolled 76 deg and
`dense-prosek-walk` 81 deg, while `dense-spotA`, whose cameras happen to form a circle,
was right to 0.4 deg. The correlation with how collinear the track is, is exact.

Gravity is the missing constraint, and there are two cheap estimates of it that need no
new sensor data:

  A. **the phones' own down axis.** People hold a phone roughly upright, so the mean of
     the camera y-axes is close to gravity. Biased by however far the photographer tilted
     the phone down, and that bias only cancels when the headings cover the circle.
  B. **the dominant planar surface under the cameras.** The ground is flat, so its normal
     is up. Unbiased where there is a floor to see, useless where there is not.

They are independent, so their disagreement is the honest error bar. This module computes
both, prefers B when it has real support and agrees with A, and refuses to guess when they
disagree wildly — a wrong up is worse than a known-bad one.
"""
import math

import numpy as np


def read_ply_xyz(path: str, max_points: int = 400_000) -> np.ndarray:
    """Positions only, from the ASCII PLY reconstruct.py writes, strided to a budget."""
    with open(path, "rb") as f:
        header, n = [], 0
        while True:
            line = f.readline()
            if not line:
                return np.zeros((0, 3))
            header.append(line)
            if line.startswith(b"element vertex"):
                n = int(line.split()[-1])
            if line.strip() == b"end_header":
                break
        step = max(1, n // max_points)
        out = []
        for i, line in enumerate(f):
            if i % step:
                continue
            p = line.split()
            if len(p) >= 3:
                out.append((float(p[0]), float(p[1]), float(p[2])))
    return np.asarray(out, dtype=np.float64)


def _plane_ransac(pts: np.ndarray, tol: float, iters: int, seed: int = 0):
    """Largest planar set, returned as (unit normal, inlier count, inlier mask)."""
    rng = np.random.default_rng(seed)
    best = (0, None)
    if len(pts) < 100:
        return None, 0, None
    for _ in range(iters):
        i = rng.integers(0, len(pts), 3)
        p0, p1, p2 = pts[i]
        n = np.cross(p1 - p0, p2 - p0)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        c = int((np.abs((pts - p0) @ n) < tol).sum())
        if c > best[0]:
            best = (c, (n, p0))
    if best[1] is None:
        return None, 0, None
    n, p0 = best[1]
    mask = np.abs((pts - p0) @ n) < tol
    q = pts[mask]
    # refit by total least squares: the RANSAC triple only has to find the right set
    _, _, vt = np.linalg.svd(q - q.mean(0), full_matrices=False)
    n = vt[2] / np.linalg.norm(vt[2])
    return n, int(mask.sum()), mask


def estimate_up(points: np.ndarray, cam_pos: np.ndarray, cam_rot: np.ndarray,
                scale_units_per_m: float) -> dict:
    """Up vector in SOLVE coordinates, plus the evidence for it.

    `points` and `cam_pos` are in solve units; `cam_rot[i]` is that camera's cam->solve
    rotation, whose second column is the direction the phone calls 'down'.
    """
    downs = cam_rot[:, :, 1]
    downs = downs / np.linalg.norm(downs, axis=1, keepdims=True)
    g_phone = downs.mean(0)
    ln = np.linalg.norm(g_phone)
    up_phone = -g_phone / ln if ln > 1e-6 else None
    # how consistently the phone was held: a big spread means A is worthless
    phone_spread = float(np.degrees(
        np.arccos(np.clip(downs @ (g_phone / max(ln, 1e-9)), -1, 1))).std()) if ln > 1e-6 else None

    up_plane, inliers, frac = None, 0, 0.0
    if len(points) > 500 and len(cam_pos) > 1:
        # candidates: near the rig but not on it, so the floor dominates and distant
        # facades do not. 6 m in solve units, via the run's own scale.
        u = 1.0 / max(scale_units_per_m, 1e-9)          # solve units per metre
        d = np.linalg.norm(points[:, None, :] - cam_pos[None, :, :], axis=2).min(1) \
            if len(cam_pos) * len(points) < 40_000_000 else None
        if d is None:
            step = max(1, len(points) // 40000)
            pts = points[::step]
            d = np.linalg.norm(pts[:, None, :] - cam_pos[None, :, :], axis=2).min(1)
        else:
            pts = points
        cand = pts[(d > 0.7 * u) & (d < 6.0 * u)]
        if len(cand) > 500:
            n, inliers, _ = _plane_ransac(cand, tol=0.05 * u, iters=2000)
            if n is not None:
                frac = inliers / len(cand)
                if up_phone is not None and n @ up_phone < 0:
                    n = -n
                up_plane = n

    disagree = None
    if up_plane is not None and up_phone is not None:
        disagree = float(np.degrees(math.acos(max(-1.0, min(1.0, float(up_plane @ up_phone))))))

    # The decision. B when it has real support and A does not contradict it; otherwise A
    # if the phone was held consistently; otherwise nothing, and the caller keeps the
    # GPS-only fit rather than being handed a guess.
    if up_plane is not None and frac > 0.05 and inliers > 2000 and (disagree is None or disagree < 30):
        up, src = up_plane, "ground-plane"
    elif up_phone is not None and (phone_spread or 99) < 20:
        up, src = up_phone, "phone-down"
    else:
        up, src = None, "none"
    return {"up": None if up is None else up.tolist(), "up_source": src,
            "up_plane": None if up_plane is None else up_plane.tolist(),
            "up_phone": None if up_phone is None else up_phone.tolist(),
            "plane_inliers": int(inliers), "plane_inlier_frac": round(float(frac), 4),
            "phone_spread_deg": None if phone_spread is None else round(phone_spread, 2),
            "disagreement_deg": None if disagree is None else round(disagree, 2)}


def _rot_a_to_b(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Minimal rotation taking unit vector a onto unit vector b."""
    v = np.cross(a, b)
    c = float(a @ b)
    s = float(np.linalg.norm(v))
    if s < 1e-12:
        return np.eye(3) if c > 0 else -np.eye(3) + 2 * np.outer(b, b)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def gravity_alignment(cams: np.ndarray, gps_enu: np.ndarray, up_solve: np.ndarray):
    """Similarity solve->ENU with up_solve pinned to +Z, everything else fitted to GPS.

    Only the HORIZONTAL components drive the yaw, scale and translation: phone GPS
    altitude is far worse than its horizontal fix, and letting it into the fit is how a
    good horizontal alignment gets dragged out of plumb. The vertical offset then simply
    puts the camera centroid at the cluster's mean altitude, which is the same convention
    the GPS-only fit used.
    """
    up = np.asarray(up_solve, dtype=float)
    up = up / np.linalg.norm(up)
    R0 = _rot_a_to_b(up, np.array([0.0, 0.0, 1.0]))
    a = (R0 @ cams.T).T
    ac, bc = a.mean(0), gps_enu.mean(0)
    A, B = a - ac, gps_enu - bc
    # 2-D Procrustes in the horizontal plane
    num = float((A[:, 0] * B[:, 1] - A[:, 1] * B[:, 0]).sum())
    den = float((A[:, 0] * B[:, 0] + A[:, 1] * B[:, 1]).sum())
    yaw = math.atan2(num, den)
    cy, sy = math.cos(yaw), math.sin(yaw)
    Rz = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]])
    rot = Rz @ R0
    ra = (Rz @ A.T).T
    denom = float((A[:, :2] ** 2).sum())
    s = float((ra[:, :2] * B[:, :2]).sum() / denom) if denom > 1e-12 else 1.0
    # NB: `ac` is already levelled by R0, so the centroid must be carried by Rz alone —
    # applying `rot` (= Rz @ R0) to it would level it twice, which silently throws the
    # whole cluster tens of metres sideways.
    cc = Rz @ ac
    t = np.array([bc[0] - s * cc[0], bc[1] - s * cc[1], -s * cc[2]])
    return s, rot, t
