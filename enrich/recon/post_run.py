#!/usr/bin/env python3
"""Finish a run from its run dir: the worker's post-solve half, runnable by hand.

WHY. reconstruct.py writes everything to the run dir; the worker then computes the
metrics, attaches the physical checks and POSTs the artifacts. When the worker's actor
dies before that half -- a time limit, a SIGTERM, a reboot -- the solve on disk is
complete and the bench never hears of it. This is that half, on its own, for exactly
those cases. Idempotent: posting the same artifacts twice just overwrites them.

Usage:  python post_run.py <run_id> [--runs-dir DIR] [--dry-run]
Reads RECON_CALLBACK_URL / ENRICH_WORKER_TOKEN / RECON_RUNS_DIR like worker.py.
"""
import argparse
import importlib
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ENRICH_SCRIPTS = os.path.join(REPO, "scripts", "enrich")
sys.path.insert(0, ENRICH_SCRIPTS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--runs-dir", default=os.getenv("RECON_RUNS_DIR",
                                                    os.path.join(ENRICH_SCRIPTS, "runs", "bench")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rundir = os.path.join(a.runs_dir, a.run_id)
    md = os.path.join(rundir, "metadata.json")
    if not os.path.exists(md):
        raise SystemExit(f"{rundir}: no metadata.json -- the solve did not finish")
    import worker
    import recon_metrics
    recon_metrics = importlib.reload(recon_metrics)
    t0 = time.time()
    metrics = recon_metrics.measure(rundir)
    for name, fn in (("ground_split", worker._ground_split), ("chain", worker._chain)):
        try:
            metrics[name] = fn(rundir)
        except Exception as e:
            metrics[name] = {"error": f"{type(e).__name__}: {e}"}
    with open(os.path.join(rundir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    recon_metrics.print_summary(metrics)
    if a.dry_run:
        print("dry run: not posting")
        return
    files, handles = {}, []
    for key, fname in (("metadata", "metadata.json"), ("metrics", "metrics.json"),
                       ("cloud", "points.ply"), ("dense_cloud", "dense.ply"),
                       ("topdown", "topdown.png"), ("pairs_matrix", "pairs_matrix.png"),
                       ("log", "run.log")):
        p = os.path.join(rundir, fname)
        if os.path.exists(p):
            fh = open(p, "rb")
            handles.append(fh)
            files[key] = (fname, fh, "application/octet-stream")
    try:
        worker._post({"result_id": a.run_id, "status": "done", "error": None,
                      "worker": socket.gethostname() + " (post_run)",
                      "n_frames": metrics.get("n_frames"), "n_pairs": metrics.get("n_pairs"),
                      "metrics": metrics,
                      "meta": {"stage": "finished", "rundir": rundir,
                               "posted_by": "post_run.py", "elapsed_s": None}}, files)
    finally:
        for fh in handles:
            fh.close()
    print(f"posted {a.run_id} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
