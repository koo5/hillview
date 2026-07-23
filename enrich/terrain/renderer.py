"""Depth-panorama renderer: synthetic terrain views from a photo's viewpoint.

Given a DSM/DEM grid and an observer (lat, lon, eye elevation), render a
cylindrical panorama where every pixel knows the DISTANCE to the visible
surface (and its elevation). The depth channel is the whole point:

  * fog becomes a per-pixel function of depth → the bench UI applies it live
    in a shader, sliders and all, with zero re-renders;
  * a click is (azimuth, depth) → forward geodesic → exact geo coordinates —
    the photo-pane "click a mountain, get its coords" story;
  * cross-referencing depth minima with OSM `natural=peak` yields automatic
    candidate annotations for the workbench pipeline (…→ anchoring → 3D).

Accuracy notes (the two things that matter at 100 km):
  * Earth curvature: a target at ground distance d appears LOWER by ~d²/(2R):
    ~590 m at 100 km. Non-negotiable.
  * Atmospheric refraction: light bends down, lifting distant terrain back up
    a bit. Standard surveying treatment: effective radius R' = R/(1-k) with
    k ≈ 0.13 for typical conditions.
  Both live in one line: angle = atan((h - h_eye)/d - d/(2·R')).

Algorithm (vectorised horizon march):
  march a shared, geometrically-growing distance schedule; at each distance,
  sample the DEM at every azimuth at once and record the apparent elevation
  angle. The running max over distance (np.maximum.accumulate) is the horizon
  profile-so-far; for each pixel row (an elevation angle), the visible surface
  is the FIRST march step whose running max reaches that angle — one
  searchsorted per column. O(steps·az) samples, all numpy.

Pure numpy core; rasterio is an optional import used only by the GeoTIFF
loaders (the worker's path). The ops pipeline that produces the DEM mosaic
(ČÚZK DMP 1G / DMR 4G → PDAL/GDAL → EPSG:4326 COG, Copernicus GLO-30 beyond
the borders) is documented in README.md next door.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

R_EARTH_M = 6_371_000.0
DEFAULT_REFRACTION_K = 0.13
DEPTH_SCALE_M = 4.0           # uint16 depth quantisation: 4 m steps, 262 km range
DEPTH_SKY = 0                 # reserved uint16 value for "no terrain hit"


def effective_radius(refraction_k: float = DEFAULT_REFRACTION_K) -> float:
    return R_EARTH_M / (1.0 - refraction_k)


# ---------------------------------------------------------------------------
# geodesy (spherical — mirrors frontend/src/lib/geo.ts so click-back results
# agree with what the main app computes)
# ---------------------------------------------------------------------------

def destination_point(lat: float, lon: float, bearing_deg, distance_m):
    """Forward geodesic on the sphere; bearing/distance may be numpy arrays."""
    d = np.asarray(distance_m, dtype=np.float64) / R_EARTH_M
    br = np.radians(np.asarray(bearing_deg, dtype=np.float64))
    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = np.arcsin(np.sin(lat1) * np.cos(d) + np.cos(lat1) * np.sin(d) * np.cos(br))
    lon2 = lon1 + np.arctan2(np.sin(br) * np.sin(d) * np.cos(lat1),
                             np.cos(d) - np.sin(lat1) * np.sin(lat2))
    return np.degrees(lat2), (np.degrees(lon2) + 540.0) % 360.0 - 180.0


# ---------------------------------------------------------------------------
# DEM grid
# ---------------------------------------------------------------------------

@dataclass
class DemGrid:
    """North-up geographic elevation grid (EPSG:4326), bilinear sampling.

    `elev[0, 0]` is the north-west pixel CENTER at (lat_top, lon_left);
    row r is at lat_top - r·dlat, column c at lon_left + c·dlon. NaN = nodata.
    """
    elev: np.ndarray          # (H, W) float32, NaN for nodata
    lat_top: float            # latitude of row-0 pixel centers
    lon_left: float           # longitude of col-0 pixel centers
    dlat: float               # > 0, degrees per row going south
    dlon: float               # > 0, degrees per column going east

    def sample(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Bilinear elevation at (lats, lons); NaN outside the grid/nodata."""
        h, w = self.elev.shape
        r = (self.lat_top - np.asarray(lats)) / self.dlat
        c = (np.asarray(lons) - self.lon_left) / self.dlon
        out = np.full(np.broadcast(r, c).shape, np.nan, dtype=np.float32)
        ok = (r >= 0) & (r <= h - 1) & (c >= 0) & (c <= w - 1)
        if not ok.any():
            return out
        r, c = np.clip(r[ok], 0, h - 1 - 1e-9), np.clip(c[ok], 0, w - 1 - 1e-9)
        r0, c0 = np.floor(r).astype(np.intp), np.floor(c).astype(np.intp)
        fr, fc = (r - r0).astype(np.float32), (c - c0).astype(np.float32)
        e = self.elev
        v = (e[r0, c0] * (1 - fr) * (1 - fc) + e[r0, c0 + 1] * (1 - fr) * fc
             + e[r0 + 1, c0] * fr * (1 - fc) + e[r0 + 1, c0 + 1] * fr * fc)
        out[ok] = v
        return out

    def cell_size_m(self, at_lat: float) -> float:
        return min(self.dlat * 111_320.0,
                   self.dlon * 111_320.0 * max(0.1, math.cos(math.radians(at_lat))))


def load_geotiff_window(path: str, lat: float, lon: float, radius_m: float) -> DemGrid:
    """Windowed read of an EPSG:4326 GeoTIFF/VRT/COG around the viewpoint.

    The mosaic-building pipeline (gdalwarp -t_srs EPSG:4326 …) guarantees a
    north-up 4326 grid; anything else is rejected loudly rather than rendered
    subtly wrong.
    """
    import rasterio                      # optional dep: worker environment only
    from rasterio.windows import from_bounds
    dr = radius_m / 111_320.0
    dlon_r = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"DEM must be EPSG:4326, got {src.crs} — re-run the mosaic pipeline")
        t = src.transform
        if abs(t.b) > 1e-12 or abs(t.d) > 1e-12 or t.e >= 0:
            raise ValueError("DEM must be a north-up, non-rotated grid")
        win = from_bounds(lon - dlon_r, lat - dr, lon + dlon_r, lat + dr,
                          transform=t).round_offsets().round_lengths()
        data = src.read(1, window=win, masked=True).astype(np.float32)
        elev = np.where(np.ma.getmaskarray(data), np.nan, np.ma.getdata(data))
        wt = src.window_transform(win)
        return DemGrid(elev=elev,
                       lat_top=wt.f + wt.e / 2.0,       # edge → row-0 center
                       lon_left=wt.c + wt.a / 2.0,
                       dlat=-wt.e, dlon=wt.a)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

@dataclass
class Panorama:
    depth: np.ndarray         # (rows, cols) float32 meters, NaN = sky
    surface_elev: np.ndarray  # (rows, cols) float32 meters, NaN = sky
    azimuths: np.ndarray      # (cols,) degrees, column centers
    elev_angles: np.ndarray   # (rows,) degrees, row centers, descending (row 0 = top)
    lat: float
    lon: float
    eye_elevation_m: float
    params: dict = field(default_factory=dict)

    def meta(self) -> dict:
        return {"width": int(self.depth.shape[1]), "height": int(self.depth.shape[0]),
                "az_start": float(self.azimuths[0]), "az_end": float(self.azimuths[-1]),
                "elev_max_deg": float(self.elev_angles[0]),
                "elev_min_deg": float(self.elev_angles[-1]),
                "lat": self.lat, "lon": self.lon,
                "eye_elevation_m": self.eye_elevation_m,
                "depth_scale_m": DEPTH_SCALE_M, **self.params}

    def pixel_to_latlon(self, col: int, row: int) -> dict | None:
        """The click-back: pixel → (azimuth, depth) → geo coords. None = sky."""
        d = float(self.depth[row, col])
        if not math.isfinite(d):
            return None
        az = float(self.azimuths[col])
        plat, plon = destination_point(self.lat, self.lon, az, d)
        return {"lat": float(plat), "lon": float(plon), "distance_m": d,
                "azimuth_deg": az, "elev_angle_deg": float(self.elev_angles[row]),
                "surface_elev_m": float(self.surface_elev[row, col])}


def distance_schedule(min_distance_m: float, max_distance_m: float,
                      min_step_m: float, rel_step: float) -> np.ndarray:
    """Geometric-ish schedule: near steps ≈ min_step (DEM-resolution work close
    in), far steps ≈ rel_step·d (constant RELATIVE depth error out far)."""
    out, d = [], float(min_distance_m)
    while d <= max_distance_m:
        out.append(d)
        d += max(min_step_m, d * rel_step)
        if len(out) > 100_000:
            raise ValueError("distance schedule exploded; loosen min_step_m/rel_step")
    return np.asarray(out, dtype=np.float64)


def render(dem: DemGrid, lat: float, lon: float, *,
           observer_height_m: float = 2.0,
           observer_elevation_m: float | None = None,
           az_start: float = 0.0, az_end: float = 360.0, az_step_deg: float = 0.05,
           elev_min_deg: float = -8.0, elev_max_deg: float = 12.0,
           elev_step_deg: float = 0.05,
           min_distance_m: float = 50.0, max_distance_m: float = 100_000.0,
           min_step_m: float | None = None, rel_step: float = 0.005,
           refraction_k: float = DEFAULT_REFRACTION_K) -> Panorama:
    """Render a depth panorama from (lat, lon) looking across [az_start, az_end)."""
    if observer_elevation_m is not None:
        eye = float(observer_elevation_m)
    else:
        ground = float(dem.sample(np.array([lat]), np.array([lon]))[0])
        if not math.isfinite(ground):
            raise ValueError("viewpoint is outside the DEM / on nodata")
        eye = ground + observer_height_m

    n_az = max(1, int(round((az_end - az_start) / az_step_deg)))
    azimuths = (az_start + (np.arange(n_az) + 0.5) * az_step_deg) % 360.0
    n_rows = max(1, int(round((elev_max_deg - elev_min_deg) / elev_step_deg)))
    elev_angles = elev_max_deg - (np.arange(n_rows) + 0.5) * elev_step_deg  # top→bottom
    pix_rad = np.radians(elev_angles)

    if min_step_m is None:
        min_step_m = max(5.0, dem.cell_size_m(lat) * 0.5)
    dists = distance_schedule(min_distance_m, max_distance_m, min_step_m, rel_step)
    r_eff2 = 2.0 * effective_radius(refraction_k)

    # march: apparent elevation angle of every (step, azimuth) sample
    ang = np.full((len(dists), n_az), -np.inf, dtype=np.float32)
    elv = np.full((len(dists), n_az), np.nan, dtype=np.float32)
    for i, d in enumerate(dists):
        plats, plons = destination_point(lat, lon, azimuths, d)
        h = dem.sample(plats, plons)
        a = np.arctan((h - eye) / d - d / r_eff2)
        hit = np.isfinite(h)
        ang[i, hit] = a[hit].astype(np.float32)
        elv[i] = h

    horizon = np.maximum.accumulate(ang, axis=0)   # running horizon profile

    depth = np.full((n_rows, n_az), np.nan, dtype=np.float32)
    surf = np.full((n_rows, n_az), np.nan, dtype=np.float32)
    n_steps = len(dists)
    for j in range(n_az):                          # tiny per-column work
        idx = np.searchsorted(horizon[:, j], pix_rad)   # first step ≥ pixel angle
        vis = idx < n_steps
        ii = idx[vis]
        depth[vis, j] = dists[ii]
        surf[vis, j] = elv[ii, j]

    return Panorama(depth=depth, surface_elev=surf, azimuths=azimuths,
                    elev_angles=elev_angles, lat=lat, lon=lon, eye_elevation_m=eye,
                    params={"refraction_k": refraction_k,
                            "max_distance_m": max_distance_m,
                            "az_step_deg": az_step_deg,
                            "elev_step_deg": elev_step_deg})


# ---------------------------------------------------------------------------
# preview shading + depth encoding
# ---------------------------------------------------------------------------

_HYPSO = np.asarray([   # elevation ramp, low→high (approx. classic hypsometric)
    (86, 139, 96), (140, 168, 108), (190, 190, 120),
    (196, 168, 116), (176, 138, 104), (222, 222, 222)], dtype=np.float32)


def shade(pano: Panorama, fog_density_per_m: float = 0.0,
          sky_rgb=(167, 205, 240)) -> np.ndarray:
    """Hypsometric preview RGB (uint8). Fog here is only for static previews —
    the bench UI applies fog live in a shader from the depth channel instead."""
    depth, elev = pano.depth, pano.surface_elev
    sky = ~np.isfinite(depth)
    e = np.where(np.isfinite(elev), elev, 0.0)
    lo, hi = np.nanpercentile(e[~sky], 2) if (~sky).any() else 0.0, \
        np.nanpercentile(e[~sky], 98) if (~sky).any() else 1.0
    t = np.clip((e - lo) / max(1.0, hi - lo), 0, 1) * (len(_HYPSO) - 1)
    i0 = np.clip(t.astype(np.intp), 0, len(_HYPSO) - 2)
    f = (t - i0)[..., None]
    rgb = _HYPSO[i0] * (1 - f) + _HYPSO[i0 + 1] * f
    # cheap relief: darken by how steeply depth grows downward (flat ground far ≈ bright)
    with np.errstate(invalid="ignore"):
        dd = np.abs(np.diff(np.log1p(np.nan_to_num(depth, nan=0.0)), axis=0, prepend=0))
    rgb *= np.clip(1.05 - 0.6 * np.clip(dd, 0, 1), 0.35, 1.05)[..., None]
    if fog_density_per_m > 0:
        fog = (1.0 - np.exp(-np.nan_to_num(depth, nan=0.0) * fog_density_per_m))[..., None]
        rgb = rgb * (1 - fog) + np.asarray(sky_rgb, np.float32) * fog
    rgb[sky] = sky_rgb
    return np.clip(rgb, 0, 255).astype(np.uint8)


def encode_depth_u16(depth: np.ndarray, scale_m: float = DEPTH_SCALE_M) -> bytes:
    """Row-major little-endian uint16, value = round(depth/scale), 0 = sky.
    Raw on purpose: browsers truncate 16-bit PNG to 8 via canvas; a raw buffer
    goes straight into a Uint16Array → WebGL texture."""
    q = np.round(np.nan_to_num(depth, nan=0.0) / scale_m)
    q = np.clip(q, 0, 65535).astype("<u2")
    q[~np.isfinite(depth)] = DEPTH_SKY
    q[(q == DEPTH_SKY) & np.isfinite(depth)] = 1     # don't lose sub-scale hits to "sky"
    return q.tobytes()


def decode_depth_u16(buf: bytes, rows: int, cols: int,
                     scale_m: float = DEPTH_SCALE_M) -> np.ndarray:
    q = np.frombuffer(buf, dtype="<u2").reshape(rows, cols).astype(np.float32)
    out = q * scale_m
    out[q == DEPTH_SKY] = np.nan
    return out
