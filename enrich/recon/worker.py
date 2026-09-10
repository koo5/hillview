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
The run dir stays here, and so does the forward-pass cache — since 2026-09-10 in the
content-addressed scripts/enrich/runs/shared_cache (reconstruct.py --cache, env
RECON_SHARED_CACHE), where a photo staged at the same size by another run is a hit. The
run dir keeps only the run-specific parts (canonical views, masked correspondences);
recon_resolve.py re-solves from those when intrinsics must be recovered.

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
import re
import socket
import queue
import subprocess
import sys
import threading
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


class Cancelled(Exception):
    """The bench cancelled this run; raised out of a progress post to stop the solve."""


def _post(payload: dict, files: dict | None = None) -> None:
    import requests
    try:
        r = requests.post(CALLBACK_URL,
                          data={"result_json": json.dumps(payload)},
                          files=files or None,
                          headers={"X-Worker-Token": WORKER_TOKEN},
                          timeout=300)
        try:
            if r.json().get("cancelled"):
                raise Cancelled()
        except (ValueError, AttributeError):
            pass
    except Cancelled:
        raise
    except Exception as e:                              # never let reporting kill the job
        print(f"  callback failed: {type(e).__name__}: {e}", flush=True)


# reconstruct.py flags this worker will pass through, with their CLI spelling. Mirrors the
# API's ALLOWED_PARAMS (defense on both ends): the broker cannot smuggle in a flag that
# would, say, redirect --out.
FLAG_PARAMS = {"win": "--win", "pairs": "--pairs", "pair_dist": "--pair_dist",
               "semantic_budget": "--semantic_budget",
               "pair_dang": "--pair_dang", "size": "--size",
               "niter1": "--niter1", "niter2": "--niter2",
               "min_conf": "--min_conf"}
BOOL_PARAMS = {"dense": "--dense", "mask_anon": "--mask_anon",
               "mask_solocator": "--mask_solocator",
               "mask_vegetation": "--mask_vegetation",
               "semantic_mask": "--semantic_mask",
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


def _kill(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.kill()
        proc.wait(timeout=10)
    except Exception:
        pass


def _ground_split(rundir: str) -> dict:
    import importlib
    import recon_ground_split
    recon_ground_split = importlib.reload(recon_ground_split)
    d = recon_ground_split.analyse(rundir, log=lambda *a: None)
    d.pop("frames", None)          # per-frame rows stay in the run dir, not the row
    return d


def _chain(rundir: str) -> dict:
    import importlib
    import recon_verify_links
    recon_verify_links = importlib.reload(recon_verify_links)
    rows, frames = recon_verify_links.judge(rundir, min_corres=1)
    return recon_verify_links.chain_summary(rows, frames)


# There is no magic wall-clock number. A CPU solve of a win-12 cluster is a ten-hour job
# when healthy, and the old six-hour limit killed exactly such a run -- badly: remoulade's
# TimeLimitExceeded unwinds the ACTOR THREAD, and the solve is a subprocess, which ran on
# as an orphan beside the next job. What decides whether a run should live is whether it
# is still PRODUCING, so the worker reads the solver's own progress bars and judges by
# rate: it posts rate and ETA to the bench, warns when the pace falls well below the run's
# own early pace (two solves sharing a box read as a 10x slowdown), and kills only when
# the solve has BURNED CPU without producing -- STALL_KILL_MIN of the child's own CPU time
# since its last progress line, not wall time. The VM this runs on can be paused: on
# resume the guest clocks jump forward, and a wall-clock stall check would kill a healthy
# solve the moment it came back. A paused solve accrues no CPU; a spinning one does. Wall
# time is still reported, next to CPU time, so the operator can tell paused from stuck.
# The actor limit that remains is a ceiling no healthy run reaches, pauses included.
TIME_LIMIT_MS = int(float(os.getenv("RECON_TIME_LIMIT_H", "720")) * 3600 * 1000)
STALL_WARN_MIN = float(os.getenv("RECON_STALL_WARN_MIN", "20"))       # wall, warn only
STALL_KILL_CPU_MIN = float(os.getenv("RECON_STALL_KILL_CPU_MIN", "120"))  # CPU, kill
SLOW_FACTOR = float(os.getenv("RECON_SLOW_FACTOR", "3.0"))

# tqdm's bar, as reconstruct.py prints it:  " 44%|████▍     | 416/948 [5:56:40<12:49:01, 86.73s/it]"
_PROGRESS = re.compile(r"(\d+)/(\d+) \[(\d+(?::\d+)+)<(\d+(?::\d+)+|\?), +([\d.]+)(s/it|it/s)")


class Progress:
    """Productivity of the running solve, read off its own progress bars.

    A solve prints several bars in sequence (the pair sweep, then two optimiser
    passes), so a new bar is detected when the total changes or the count resets, and
    the baseline pace is measured per bar from its first few iterations."""

    def __init__(self, pid=None):
        self.done = self.total = 0
        self.s_per_it = None
        self.baseline = None          # median s/it over the bar's first samples
        self.samples = []
        self.last_line_at = time.monotonic()
        self.last_progress_at = time.monotonic()
        self.bars = 0
        self.warning = None
        self.pid = pid
        self.cpu_at_progress = self.cpu_s()
        self.wall0 = time.time()

    def cpu_s(self) -> float:
        """The child's cumulative CPU seconds, children included. 0 if it is gone."""
        if not self.pid:
            return 0.0
        try:
            import psutil
            p = psutil.Process(self.pid)
            t = p.cpu_times()
            tot = t.user + t.system
            for c in p.children(recursive=True):
                try:
                    ct = c.cpu_times()
                    tot += ct.user + ct.system
                except psutil.Error:
                    pass
            return float(tot)
        except Exception:
            return 0.0

    def feed(self, line: str) -> None:
        self.last_line_at = time.monotonic()
        m = _PROGRESS.search(line)
        if not m:
            return
        done, total = int(m.group(1)), int(m.group(2))
        rate = float(m.group(5))
        s_per_it = rate if m.group(6) == "s/it" else (1.0 / rate if rate else None)
        if total != self.total or done < self.done:
            self.bars += 1
            self.samples, self.baseline = [], None
        if done > self.done:
            self.last_progress_at = time.monotonic()
            self.cpu_at_progress = self.cpu_s()
        self.done, self.total, self.s_per_it = done, total, s_per_it
        if s_per_it is not None and self.baseline is None:
            self.samples.append(s_per_it)
            if len(self.samples) >= 20:
                self.baseline = sorted(self.samples)[len(self.samples) // 2]
        self.warning = None
        if self.baseline and s_per_it and s_per_it > SLOW_FACTOR * self.baseline:
            self.warning = (f"{s_per_it / self.baseline:.1f}x slower than this run's own early "
                            f"pace ({self.baseline:.0f} s/it) — another solve on the box?")

    def stalled_min(self) -> float:
        """Wall minutes since the last progress line. Jumps across a VM pause: warn only."""
        return (time.monotonic() - self.last_progress_at) / 60.0

    def stalled_cpu_min(self) -> float:
        """CPU minutes the solve has burned since its last progress line. This is the
        stall that means something: it does not move while the VM is paused."""
        return max(0.0, self.cpu_s() - self.cpu_at_progress) / 60.0

    def eta_s(self):
        if not self.s_per_it or not self.total:
            return None
        return int((self.total - self.done) * self.s_per_it)

    def meta(self) -> dict:
        cpu = self.cpu_s()
        d = {"done": self.done, "total": self.total, "bar": self.bars,
             "s_per_it": None if self.s_per_it is None else round(self.s_per_it, 1),
             "eta_s": self.eta_s(),
             "cpu_s": round(cpu), "wall_s": round(time.time() - self.wall0)}
        w = self.warning
        st, sc = self.stalled_min(), self.stalled_cpu_min()
        if st > STALL_WARN_MIN and self.total:
            w = (f"no progress for {st:.0f} min wall / {sc:.0f} min cpu"
                 + (" — paused, not stuck" if sc < st / 4 else "")
                 + (f"; {w}" if w else ""))
        return {"progress": d, "warning": w}


@remoulade.actor(queue_name="recon", time_limit=TIME_LIMIT_MS, max_retries=0)
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

    try:
        _post({"result_id": rid, "status": "running", "worker": socket.gethostname(),
               "n_frames": len(frames),
               "meta": {"stage": "queued", "rundir": rundir}})
    except Cancelled:
        # cancelled (or already done) before it started: a duplicate or stale message
        print(f"  {rid} '{name}' skipped: the bench says cancelled/done", flush=True)
        return

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
    proc = None
    try:
        ram_gate()
        print(f"  $ {' '.join(cmd)}", flush=True)
        # cwd so reconstruct.py's default mast3r_repo/ resolution works even without the
        # env overrides; stderr folded in so a traceback lands in the same log the bench
        # serves back.
        with open(log_path, "w") as lf:
            proc = subprocess.Popen(cmd, cwd=ENRICH_SCRIPTS, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            # A reader thread, because `for line in proc.stdout` blocks: a solve that has
            # gone silent could never be noticed from inside its own read loop.
            q: "queue.Queue[str | None]" = queue.Queue()

            def _reader():
                for line in proc.stdout:
                    q.put(line)
                q.put(None)
            threading.Thread(target=_reader, daemon=True).start()
            last_post, stage = 0.0, "starting"
            prog = Progress(pid=proc.pid)
            while True:
                try:
                    line = q.get(timeout=30)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line:
                    lf.write(line)
                    lf.flush()
                    print(f"  | {line.rstrip()}", flush=True)
                    stage = _stage_for(line) or stage
                    prog.feed(line)
                if prog.total and prog.stalled_cpu_min() > STALL_KILL_CPU_MIN:
                    _kill(proc)
                    raise RuntimeError(
                        f"stalled: {prog.stalled_cpu_min():.0f} min of CPU without progress "
                        f"({prog.stalled_min():.0f} min wall) at {prog.done}/{prog.total} "
                        f"(bar {prog.bars})")
                now = time.monotonic()
                if now - last_post > PROGRESS_EVERY_S:
                    last_post = now
                    pm = prog.meta()
                    if pm["warning"]:
                        print(f"  WARNING {pm['warning']}", flush=True)
                    _post({"result_id": rid, "status": "running",
                           "worker": socket.gethostname(),
                           "meta": {"stage": stage,
                                    "elapsed_s": round(time.time() - t0), **pm}})
            code = proc.wait()
        if code != 0:
            status = "error"
            with open(log_path) as lf:
                tail = "".join(lf.readlines()[-12:]).strip()
            error = f"reconstruct.py exited {code}\n{tail}"
    except Cancelled:
        # the bench said stop; kill the subprocess if one is up and report nothing more
        _kill(proc)
        print(f"  {rid} cancelled by the bench", flush=True)
        return
    except BaseException as e:
        # BaseException on purpose: remoulade's time limit and a SIGTERM both arrive as
        # exceptions that are not Exception subclasses in every version, and whichever way
        # this thread dies the solve must die with it or it runs on as an orphan
        _kill(proc)
        status, error = "error", f"{type(e).__name__}: {e}"
        print(f"  FAILED: {error}", flush=True)
        if not isinstance(e, Exception):
            _post({"result_id": rid, "status": "error", "error": error,
                   "worker": socket.gethostname(),
                   "meta": {"stage": "killed", "elapsed_s": round(time.time() - t0)}})
            raise

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
            # The physical checks ride along in metrics.json so the bench shows them for
            # every run without an operator running scripts by hand: ground agreement
            # (camera height, neighbour disagreement in cm) and the two-view chain
            # (breaks, spans, verdicts). Each is its own try: neither may sink the run.
            for name, fn in (("ground_split", _ground_split), ("chain", _chain)):
                try:
                    metrics[name] = fn(rundir)
                except Exception as e:
                    metrics[name] = {"error": f"{type(e).__name__}: {e}"}
                    print(f"  {name} failed: {metrics[name]['error']}", flush=True)
            with open(os.path.join(rundir, "metrics.json"), "w") as f:
                json.dump(metrics, f, indent=1)
            recon_metrics.print_summary(metrics)
        except Exception as e:
            status, error = "error", f"metrics failed: {type(e).__name__}: {e}"
            print(f"  {error}", flush=True)

    files, handles = {}, []
    for key, fname in (("metadata", "metadata.json"), ("metrics", "metrics.json"),
                       ("cloud", "points.ply"), ("dense_cloud", "dense.ply"),
                       ("soft_cloud", "dense_soft.ply"),
                       ("topdown", "topdown.png"),
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
