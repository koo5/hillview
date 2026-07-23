"""Terrain depth-panorama worker — renders synthetic views from photo viewpoints.

Untrusted-worker topology (cf. matcher/worker.py): consumes `render_panorama`
jobs from RabbitMQ, renders against a LOCAL DEM mosaic, and POSTs results
(depth buffer + preview JPEG + meta) back to the API with a token. No DB
credentials — the same shape a rented box will use, pointed at a tunneled broker.

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

Run (from repo root, any venv with numpy+rasterio+pillow+remoulade+requests):
    cd enrich/terrain && python -m remoulade worker --processes 1 --threads 1
or under the systemd memory scope:  ./run_worker.sh
"""
import io
import json
import os
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


def _render(lat: float, lon: float, params: dict):
    import math

    import numpy as np
    import renderer
    if not DSM_PATH:
        raise RuntimeError("TERRAIN_DSM_PATH not set (see enrich/terrain/README.md)")
    params = dict(params or {})
    gps_alt, gps_datum = params.pop("gps_altitude_m", None), params.pop("gps_datum", "auto")
    kwargs = {k: v for k, v in params.items() if k in RENDER_KEYS}
    max_d = float(kwargs.get("max_distance_m", 100_000.0))
    dem = _load_stack(renderer, DSM_PATH, lat, lon, max_d * 1.05)

    # refinement #1+2: ground the observer on bare earth, resolve GPS hints
    ground_src = "dtm" if DTM_PATH else "dsm"
    gdem = _load_stack(renderer, DTM_PATH, lat, lon, 500.0) if DTM_PATH else dem
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

    pano = renderer.render(dem, lat, lon, **kwargs)
    pano.params.update({"eye_source": eye_source,
                        "ground_m": round(ground, 2), "ground_source": ground_src})
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(renderer.shade(pano)).save(buf, "JPEG", quality=88)
    return pano.meta(), renderer.encode_depth_u16(pano.depth), buf.getvalue()


@remoulade.actor(queue_name="terrain", time_limit=20 * 60 * 1000, max_retries=1)
def render_panorama(payload: dict) -> None:
    import requests
    rid = payload["result_id"]
    print(f"render_panorama {rid} @ ({payload.get('lat')}, {payload.get('lon')})…",
          flush=True)
    result = {"result_id": rid, "worker": socket.gethostname(), "status": "done"}
    depth = preview = None
    try:
        ram_gate()
        meta, depth, preview = _render(
            float(payload["lat"]), float(payload["lon"]), payload.get("params") or {})
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
    requests.post(payload["callback"],
                  data={"result_json": json.dumps(result)},
                  files=files or None,
                  headers={"X-Worker-Token": payload["token"]},
                  timeout=120)


remoulade.declare_actors([render_panorama])
