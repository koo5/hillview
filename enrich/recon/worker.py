"""Recon worker — runs MASt3R-SfM reconstructions for the workbench's recon bench.

Untrusted-worker topology (cf. terrain/worker.py): consumes `reconstruct_cluster` jobs
from RabbitMQ, reconstructs with the LOCAL scripts/enrich stack, and POSTs the sparse
layer back to the API with a token. No DB credentials — the API selects the cluster and
ships an explicit frame manifest, so this process never needs to know how to find photos.
That is also the shape a rented GPU box will use against a tunneled broker.

The callback URL and worker token come from THIS process's environment, never from the
queue message, so a compromised broker can neither redirect the artifacts nor learn the
token.

WHY A SUBPROCESS. reconstruct.py has no callable entry point: everything lives in main()
behind argparse, it raises SystemExit in three places (a BaseException, so `except
Exception` in an actor would miss it), and it leaves module globals and a monkey-patched
`sparse_ga.forward_mast3r` behind — repeated in-process runs are not idempotent. Driving
it as a subprocess fixes all of that, makes cancellation a kill, and turns its print-only
progress into a capturable log.

WHAT COMES BACK. Only the sparse layer (metadata/metrics/points.ply/renders/log, ~16 MB).
The run dir and its 1.8-2.7 GB forward-pass cache stay here: regenerable, and needed only
to re-solve — which is exactly what recon_resolve.py does when intrinsics must be
recovered.

Environment:
    RABBITMQ_URL         default enrich:enrich@127.0.0.1:5672
    RECON_CALLBACK_URL   where results are POSTed
                         (default http://127.0.0.1:8070/api/recon/result)
    ENRICH_WORKER_TOKEN  X-Worker-Token for the callback
    RECON_RUNS_DIR       where run dirs are created (default scripts/enrich/runs/bench)
    RECON_REQUIRED_GB    RAM gate threshold before the heavy phase (default 8)
    MAST3R_REPO / MAST3R_CKPT   passed through to reconstruct.py

Run:  cd enrich/recon && python -m remoulade worker --threads 1
or under the systemd memory ceiling:  ./run_worker.sh
"""
import json
import os
import socket
import subprocess
import sys
import time

import remoulade
from remoulade.brokers.rabbitmq import RabbitmqBroker

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ENRICH_SCRIPTS = os.path.join(REPO, "scripts", "enrich")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "enrich:enrich@127.0.0.1:5672")
CALLBACK_URL = os.getenv("RECON_CALLBACK_URL",
                         "http://127.0.0.1:8070/api/recon/result")
WORKER_TOKEN = os.getenv("ENRICH_WORKER_TOKEN", "dev-worker-token")
RUNS_DIR = os.getenv("RECON_RUNS_DIR", os.path.join(ENRICH_SCRIPTS, "runs", "bench"))
REQUIRED_GB = float(os.getenv("RECON_REQUIRED_GB", "8"))
RAM_GATE_TIMEOUT_S = float(os.getenv("RECON_RAM_GATE_TIMEOUT_S", "900"))
PROGRESS_EVERY_S = float(os.getenv("RECON_PROGRESS_EVERY_S", "30"))

broker = RabbitmqBroker(url=f"amqp://{RABBITMQ_URL}?timeout=15", confirm_delivery=True)
remoulade.set_broker(broker)


def ram_gate(required_gb: float = REQUIRED_GB,
             timeout_s: float = RAM_GATE_TIMEOUT_S) -> None:
    """Wait for real headroom before the heavy phase; fail VISIBLY on timeout rather than
    blocking forever (the error travels back through the callback). Belt half — braces is
    the systemd MemoryMax in run_worker.sh, which kills only this unit."""
    import psutil
    t0 = time.monotonic()
    while True:
        avail = psutil.virtual_memory().available / 2**30
        if avail >= required_gb:
            return
        if time.monotonic() - t0 > timeout_s:
            raise MemoryError(
                f"RAM gate: only {avail:.1f} GiB available "
                f"(< {required_gb} GiB required) for {timeout_s:.0f}s")
        print(f"ram_gate: {avail:.1f} < {required_gb} GiB, waiting…", flush=True)
        time.sleep(10)


def _post(payload: dict, files: dict | None = None) -> None:
    import requests
    try:
        requests.post(CALLBACK_URL,
                      data={"result_json": json.dumps(payload)},
                      files=files or None,
                      headers={"X-Worker-Token": WORKER_TOKEN},
                      timeout=300)
    except Exception as e:                              # never let reporting kill the job
        print(f"  callback failed: {type(e).__name__}: {e}", flush=True)


# reconstruct.py flags this worker will pass through, with their CLI spelling. Mirrors the
# API's ALLOWED_PARAMS (defense on both ends): the broker cannot smuggle in a flag that
# would, say, redirect --out.
FLAG_PARAMS = {"win": "--win", "pairs": "--pairs", "pair_dist": "--pair_dist",
               "pair_dang": "--pair_dang", "size": "--size",
               "niter1": "--niter1", "niter2": "--niter2",
               "min_conf": "--min_conf"}
BOOL_PARAMS = {"dense": "--dense", "mask_anon": "--mask_anon",
               "mask_solocator": "--mask_solocator",
               "shared_intrinsics": "--shared_intrinsics"}

# lines worth reporting as progress — reconstruct.py only prints, so this is the interface
STAGE_MARKERS = (
    ("manifest:", "selected"),
    ("dl ", "downloading"),
    ("loading MASt3R", "loading model"),
    ("pairs (", "pairing"),
    ("sparse_global_alignment", "solving"),
    ("sparse points", "extracting"),
    ("extracting dense", "densifying"),
    ("aligning", "aligning to GPS"),
    ("wrote", "writing artifacts"),
)


def _stage_for(line: str) -> str | None:
    for needle, stage in STAGE_MARKERS:
        if needle in line:
            return stage
    return None


@remoulade.actor(queue_name="recon", time_limit=6 * 60 * 60 * 1000, max_retries=0)
def reconstruct_cluster(payload: dict) -> None:
    rid = payload["result_id"]
    name = payload.get("name") or rid[:8]
    frames = payload.get("frames") or []
    params = payload.get("params") or {}
    lat, lon = payload["center"]
    print(f"reconstruct_cluster {rid} '{name}': {len(frames)} frames", flush=True)

    rundir = os.path.join(RUNS_DIR, rid)
    os.makedirs(rundir, exist_ok=True)
    log_path = os.path.join(rundir, "run.log")
    manifest_path = os.path.join(rundir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump({"frames": frames}, f)

    _post({"result_id": rid, "status": "running", "worker": socket.gethostname(),
           "n_frames": len(frames),
           "meta": {"stage": "queued", "rundir": rundir}})

    cmd = [sys.executable, os.path.join(ENRICH_SCRIPTS, "reconstruct.py"),
           "--manifest", manifest_path, "--out", rundir,
           "--center", f"{lat},{lon}"]
    for key, flag in FLAG_PARAMS.items():
        if params.get(key) is not None:
            cmd += [flag, str(params[key])]
    for key, flag in BOOL_PARAMS.items():
        if params.get(key):
            cmd.append(flag)

    t0 = time.time()
    status, error, metrics = "done", None, None
    try:
        ram_gate()
        print(f"  $ {' '.join(cmd)}", flush=True)
        # cwd so reconstruct.py's default mast3r_repo/ resolution works even without the
        # env overrides; stderr folded in so a traceback lands in the same log the bench
        # serves back.
        with open(log_path, "w") as lf:
            proc = subprocess.Popen(cmd, cwd=ENRICH_SCRIPTS, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            last_post, stage = 0.0, "starting"
            for line in proc.stdout:
                lf.write(line)
                lf.flush()
                print(f"  | {line.rstrip()}", flush=True)
                stage = _stage_for(line) or stage
                now = time.monotonic()
                if now - last_post > PROGRESS_EVERY_S:
                    last_post = now
                    _post({"result_id": rid, "status": "running",
                           "worker": socket.gethostname(),
                           "meta": {"stage": stage,
                                    "elapsed_s": round(time.time() - t0)}})
            code = proc.wait()
        if code != 0:
            status = "error"
            with open(log_path) as lf:
                tail = "".join(lf.readlines()[-12:]).strip()
            error = f"reconstruct.py exited {code}\n{tail}"
    except Exception as e:
        status, error = "error", f"{type(e).__name__}: {e}"
        print(f"  FAILED: {error}", flush=True)

    # Metrics are the point of a run, so compute them here rather than making the bench
    # do it: the cache they need lives on this box and is never uploaded.
    if status == "done":
        try:
            if ENRICH_SCRIPTS not in sys.path:
                sys.path.insert(0, ENRICH_SCRIPTS)
            import recon_metrics
            # The module is cached for the life of this long-lived worker process, so an
            # edit to recon_metrics.py does NOT reach jobs already-imported here — reload
            # so a metric fix lands on the next job instead of after a worker restart.
            import importlib
            recon_metrics = importlib.reload(recon_metrics)
            metrics = recon_metrics.measure(rundir)
            with open(os.path.join(rundir, "metrics.json"), "w") as f:
                json.dump(metrics, f, indent=1)
            recon_metrics.print_summary(metrics)
        except Exception as e:
            status, error = "error", f"metrics failed: {type(e).__name__}: {e}"
            print(f"  {error}", flush=True)

    files, handles = {}, []
    for key, fname in (("metadata", "metadata.json"), ("metrics", "metrics.json"),
                       ("cloud", "points.ply"), ("topdown", "topdown.png"),
                       ("pairs_matrix", "pairs_matrix.png"), ("log", "run.log")):
        p = os.path.join(rundir, fname)
        if os.path.exists(p):
            fh = open(p, "rb")
            handles.append(fh)
            files[key] = (fname, fh, "application/octet-stream")
    try:
        _post({"result_id": rid, "status": status, "error": error,
               "worker": socket.gethostname(),
               "n_frames": (metrics or {}).get("n_frames", len(frames)),
               "n_pairs": (metrics or {}).get("n_pairs"),
               "metrics": metrics,
               "meta": {"stage": "finished", "rundir": rundir,
                        "elapsed_s": round(time.time() - t0)}}, files)
    finally:
        for fh in handles:
            fh.close()
    print(f"  {rid} {status} in {time.time() - t0:.0f}s", flush=True)


remoulade.declare_actors([reconstruct_cluster])
