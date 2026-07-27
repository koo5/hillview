"""Terrain depth-panorama worker — renders synthetic views from photo viewpoints.

Untrusted-worker topology (cf. matcher/worker.py): consumes `render_panorama`
jobs from RabbitMQ, renders against a LOCAL DEM mosaic, and POSTs results
(depth buffer + preview JPEG + meta) back to the API with a token. No DB
credentials — the same shape a rented box will use, pointed at a tunneled broker.

The callback URL and worker token come from THIS process's environment, never
from the queue message: a compromised broker can neither redirect the artifact
POST nor learn the token from payloads (deliberate divergence from matcher).

Environment:
    TERRAIN_DSM_PATH   surface mosaic(s) marched by the rays — colon-separated
                       EPSG:4326 COG/VRT entries, FINEST FIRST, each optionally
                       "path@radius_m" to cap that layer's windowed read (the
                       near/far resolution rings). Built by build_mosaic.py.
                       (legacy alias: TERRAIN_DEM_PATH)
    TERRAIN_DTM_PATH   optional bare-earth mosaic(s), same syntax — grounds the
                       OBSERVER (standing on a DSM means standing on canopy)
    TERRAIN_GEOID_OFFSET_M  ellipsoidal→orthometric offset for GPS altitude
                       plausibility (default 44.5, the CZ undulation)
    RABBITMQ_URL       default enrich:enrich@127.0.0.1:5672
    TERRAIN_CALLBACK_URL    where results are POSTed
                       (default http://127.0.0.1:8070/api/terrain/result)
    ENRICH_WORKER_TOKEN     X-Worker-Token for the callback
    TERRAIN_ATTRIBUTION     data-source credit stamped into each render's
                       meta.attribution — set to whatever the licences of the
                       mosaics behind TERRAIN_DSM_PATH require (the GLO-30
                       licence mandates a notice on derived works; ČÚZK is
                       CC BY). The UIs display it wherever renders are shown.
    TERRAIN_DSM_PATH_<STACK> / TERRAIN_DTM_PATH_<STACK> /
    TERRAIN_ATTRIBUTION_<STACK>
                       named stacks the client selects per render via the
                       `dsm_stack` param (e.g. GLO30, CUZK). DTM/attribution
                       fall back to the globals; a requested stack without a
                       DSM path fails the render visibly.

Run (from repo root; venv per requirements.txt — hash-pinned, see README):
    cd enrich/terrain && python -m remoulade worker --processes 1 --threads 1
or under the systemd memory scope:  ./run_worker.sh
"""
import io
import json
import os
import re
import socket
import sys

import remoulade
from remoulade.brokers.rabbitmq import RabbitmqBroker

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

DSM_PATH = os.getenv("TERRAIN_DSM_PATH", os.getenv("TERRAIN_DEM_PATH", ""))
DTM_PATH = os.getenv("TERRAIN_DTM_PATH", "")
GEOID_OFFSET_M = float(os.getenv("TERRAIN_GEOID_OFFSET_M", "44.5"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "enrich:enrich@127.0.0.1:5672")
REQUIRED_GB = float(os.getenv("TERRAIN_REQUIRED_GB", "2"))
RAM_GATE_TIMEOUT_S = float(os.getenv("TERRAIN_RAM_GATE_TIMEOUT_S", "600"))
CALLBACK_URL = os.getenv("TERRAIN_CALLBACK_URL",
                         "http://127.0.0.1:8070/api/terrain/result")
WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")
ATTRIBUTION = os.getenv("TERRAIN_ATTRIBUTION", "")

broker = RabbitmqBroker(url=f"amqp://{RABBITMQ_URL}?timeout=15", confirm_delivery=True)
remoulade.set_broker(broker)


def ram_gate(required_gb: float = REQUIRED_GB,
             timeout_s: float = RAM_GATE_TIMEOUT_S) -> None:
    """Belt half of the OOM protection (braces = run_worker.sh MemoryMax scope):
    wait for headroom, then FAIL VISIBLY instead of blocking forever."""
    import time

    import psutil
    t0 = time.monotonic()
    while True:
        avail_gb = psutil.virtual_memory().available / 2**30
        if avail_gb >= required_gb:
            return
        if time.monotonic() - t0 > timeout_s:
            raise MemoryError(
                f"RAM gate: only {avail_gb:.1f} GiB available "
                f"(< {required_gb} GiB required) for {timeout_s:.0f}s")
        print(f"ram_gate: {avail_gb:.1f} < {required_gb} GiB, waiting…", flush=True)
        time.sleep(5)


# render() kwargs the API is allowed to pass through — everything else is
# dropped so a stray payload can't reach exotic renderer internals. GPS hints
# (gps_altitude_m, gps_datum) are NOT render() kwargs: they are resolved here
# against the terrain ground into observer_elevation_m.
RENDER_KEYS = {"observer_height_m", "observer_elevation_m",
               "az_start", "az_end", "az_step_deg",
               "elev_min_deg", "elev_max_deg", "elev_step_deg",
               "min_distance_m", "max_distance_m", "rel_step", "refraction_k"}


def _parse_layers(spec: str) -> list[tuple[str, float | None]]:
    """'path[@radius_m]:path…' → [(path, radius_cap_or_None), …], finest first."""
    out = []
    for entry in spec.split(":"):
        if not entry:
            continue
        path, _, rad = entry.partition("@")
        out.append((path, float(rad) if rad else None))
    return out


def _load_stack(renderer, spec: str, lat: float, lon: float, radius_m: float):
    grids = [renderer.load_geotiff_window(p, lat, lon,
                                          min(radius_m, cap) if cap else radius_m)
             for p, cap in _parse_layers(spec)]
    return grids[0] if len(grids) == 1 else renderer.CompositeDem(grids=grids)


STACK_RE = re.compile(r"[a-z0-9_]{1,32}\Z")


def _resolve_stack(params: dict) -> tuple[str, str, str, str]:
    """Per-render DSM stack selection: the client's `dsm_stack` param picks
    TERRAIN_DSM_PATH_<STACK> (+ per-stack DTM/attribution, falling back to
    the globals). No param → the default env stack, exactly as before. An
    unknown or unconfigured stack raises — the render fails VISIBLY in the
    UI instead of silently using the wrong data. → (dsm, dtm, attribution,
    stack_name)."""
    stack = params.pop("dsm_stack", None)
    if stack is None:
        return DSM_PATH, DTM_PATH, ATTRIBUTION, "default"
    stack = str(stack).lower()
    if not STACK_RE.match(stack):
        raise RuntimeError(f"bad dsm_stack {stack!r}")
    s = stack.upper()
    dsm = os.getenv(f"TERRAIN_DSM_PATH_{s}", "")
    if not dsm:
        raise RuntimeError(f"DSM stack '{stack}' not configured on this worker "
                           f"(set TERRAIN_DSM_PATH_{s})")
    return (dsm,
            os.getenv(f"TERRAIN_DTM_PATH_{s}", "") or DTM_PATH,
            os.getenv(f"TERRAIN_ATTRIBUTION_{s}", "") or ATTRIBUTION,
            stack)


def _render(lat: float, lon: float, params: dict, progress=None, checkpoint=None):
    import math

    import numpy as np
    import renderer
    params = dict(params or {})
    dsm_path, dtm_path, attribution, stack = _resolve_stack(params)
    if not dsm_path:
        raise RuntimeError("TERRAIN_DSM_PATH not set (see enrich/terrain/README.md)")
    gps_alt, gps_datum = params.pop("gps_altitude_m", None), params.pop("gps_datum", "auto")
    kwargs = {k: v for k, v in params.items() if k in RENDER_KEYS}
    # worker default grid: 2× the renderer's 0.05° in both axes — combined
    # with elevation auto-fit and pie-limited sweeps the pixels go where the
    # view is, so the finer default stays affordable
    kwargs.setdefault("az_step_deg", 0.025)
    kwargs.setdefault("elev_step_deg", 0.025)
    max_d = float(kwargs.get("max_distance_m", 100_000.0))
    dem = _load_stack(renderer, dsm_path, lat, lon, max_d * 1.05)

    # refinement #1+2: ground the observer on bare earth, resolve GPS hints
    ground_src = "dtm" if dtm_path else "dsm"
    gdem = _load_stack(renderer, dtm_path, lat, lon, 500.0) if dtm_path else dem
    ground = float(gdem.sample(np.array([lat]), np.array([lon]))[0])
    if not math.isfinite(ground):
        raise RuntimeError("viewpoint outside the DEM / on nodata")
    if "observer_elevation_m" not in kwargs:
        eye, eye_source = renderer.resolve_eye_elevation(
            ground, observer_height_m=float(kwargs.get("observer_height_m", 2.0)),
            gps_altitude_m=gps_alt, gps_datum=gps_datum,
            geoid_offset_m=GEOID_OFFSET_M)
        kwargs["observer_elevation_m"] = eye
    else:
        eye_source = "explicit"

    # Auto-fit the elevation window when the caller didn't pin one: the
    # static default (−8..+12°) wastes most rows on empty sky from lowland
    # viewpoints. A coarse probe (1° azimuth grid ≈ 5% of the render cost)
    # finds the highest horizon point; the top clamps to it + margin (sky
    # labels float above the skyline, so leave them headroom).
    elev_fit = "explicit"
    if "elev_max_deg" not in kwargs and "elev_min_deg" not in kwargs:
        probe_kwargs = {k: kwargs[k] for k in
                        ("observer_elevation_m", "max_distance_m",
                         "min_distance_m", "rel_step", "refraction_k")
                        if k in kwargs}
        probe = renderer.render(dem, lat, lon, az_step_deg=1.0,
                                elev_step_deg=0.25, elev_min_deg=-10.0,
                                elev_max_deg=25.0, **probe_kwargs)
        rows = np.nonzero(np.isfinite(probe.depth).any(axis=1))[0]
        top_elev = float(probe.elev_angles[rows[0]]) if rows.size else 0.0
        kwargs["elev_max_deg"] = max(top_elev + 1.5, 1.0)
        # bottom fit: rows where EVERY column is nearer than 300 m are
        # featureless foreground (grass at your feet) — trim them too
        far_per_row = np.where(np.isfinite(probe.depth), probe.depth, 0.0).max(axis=1)
        far_rows = np.nonzero(far_per_row >= 300.0)[0]
        if far_rows.size:
            bottom_elev = float(probe.elev_angles[far_rows[-1]])
            kwargs["elev_min_deg"] = max(min(-1.0, bottom_elev - 0.5), -10.0)
        # row budget: fine sector steps × a tall fitted window would blow past
        # mobile GPU texture limits (seen: 7500 rows at 0.0025°). Keep the
        # skyline, crop the foreground.
        MAX_ROWS = 4000.0
        step = float(kwargs["elev_step_deg"])
        lo = kwargs.get("elev_min_deg", -8.0)
        if (kwargs["elev_max_deg"] - lo) / step > MAX_ROWS:
            kwargs["elev_min_deg"] = kwargs["elev_max_deg"] - MAX_ROWS * step
        elev_fit = (f"auto ({kwargs.get('elev_min_deg', -8.0):.1f}"
                    f"..{kwargs['elev_max_deg']:.1f}°, horizon {top_elev:.2f}°)")

    pano = renderer.render(dem, lat, lon, progress=progress, checkpoint=checkpoint,
                           **kwargs)
    pano.params.update({"eye_source": eye_source, "dsm_stack": stack,
                        "elev_fit": elev_fit,
                        "ground_m": round(ground, 2), "ground_source": ground_src})
    if attribution:
        pano.params["attribution"] = attribution
    return pano.meta(), renderer.encode_depth_u16(pano.depth), _preview_jpeg(pano)


def _preview_jpeg(pano) -> bytes:
    import renderer
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(renderer.shade(pano)).save(buf, "JPEG", quality=88)
    return buf.getvalue()


@remoulade.actor(queue_name="terrain", time_limit=20 * 60 * 1000, max_retries=1)
def render_panorama(payload: dict) -> None:
    import time

    import requests
    rid = payload["result_id"]
    print(f"render_panorama {rid} @ ({payload.get('lat')}, {payload.get('lon')})…",
          flush=True)
    result = {"result_id": rid, "worker": socket.gethostname(), "status": "done"}
    depth = preview = None

    # Progress ship-order step 1 (docs/terrain-mode.md): tiny JSON pings on
    # the SAME callback, status "rendering", % riding in the meta jsonb (the
    # final result overwrites it). Throttled to ~2 s so a fast render doesn't
    # spam; failures are swallowed — progress must never fail a render.
    last_progress_post = 0.0

    def _post_rendering(meta: dict, files: dict | None) -> None:
        requests.post(CALLBACK_URL,
                      data={"result_json": json.dumps({
                          "result_id": rid, "status": "rendering",
                          "worker": socket.gethostname(), "meta": meta})},
                      files=files or None,
                      headers={"X-Worker-Token": WORKER_TOKEN},
                      timeout=30)

    def post_progress(frac: float) -> None:
        nonlocal last_progress_post
        now = time.monotonic()
        if now - last_progress_post < 2.0:
            return
        last_progress_post = now
        try:
            _post_rendering({"progress_pct": int(frac * 100)}, None)
        except Exception as e:
            print(f"  {rid}: progress post failed: {e}", flush=True)

    def post_partial(pano, frac: float) -> None:
        """v1.5 flourish (docs/terrain-mode.md): a milestone partial is a
        valid panorama, so ship it — full grid meta + artifacts, still
        status 'rendering'. artifact_version (merged into the meta jsonb,
        surviving later %-only pings) is what tells clients NEW artifacts
        landed, so mobile re-downloads at ~4 milestones, not per ping."""
        pct = int(frac * 100)
        try:
            _post_rendering(
                pano.meta() | {"progress_pct": pct, "artifact_version": pct},
                {"depth": ("depth.bin", renderer_encode(pano),
                           "application/octet-stream"),
                 "preview": ("preview.jpg", _preview_jpeg(pano), "image/jpeg")})
            print(f"  {rid}: partial @ {pct}%", flush=True)
        except Exception as e:
            print(f"  {rid}: partial post failed: {e}", flush=True)

    def renderer_encode(pano) -> bytes:
        import renderer
        return renderer.encode_depth_u16(pano.depth)

    try:
        ram_gate()
        meta, depth, preview = _render(
            float(payload["lat"]), float(payload["lon"]), payload.get("params") or {},
            progress=post_progress, checkpoint=post_partial)
        result["meta"] = meta
        print(f"  {rid}: {meta['width']}x{meta['height']}", flush=True)
    except Exception as e:
        result.update({"status": "error", "error": f"{type(e).__name__}: {e}"})
        print(f"  {rid} FAILED: {e}", flush=True)
    files = {}
    if depth is not None:
        files["depth"] = ("depth.bin", depth, "application/octet-stream")
    if preview is not None:
        files["preview"] = ("preview.jpg", preview, "image/jpeg")
    requests.post(CALLBACK_URL,
                  data={"result_json": json.dumps(result)},
                  files=files or None,
                  headers={"X-Worker-Token": WORKER_TOKEN},
                  timeout=120)


remoulade.declare_actors([render_panorama])
