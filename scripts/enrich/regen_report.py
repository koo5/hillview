#!/usr/bin/env python3
"""Regenerate report.html for a finished run from its metadata.json (no recompute)."""
import sys, json, os
import reconstruct as R

def regen(rundir):
    m = json.load(open(os.path.join(rundir, "metadata.json")))
    frames = m["frames"]
    sub = [{"id": f["id"], "cap": f["captured_at"] or "", "brg": f["compass_angle"],
            "ttl": f["title"], "inj": f.get("injected")} for f in frames]
    gps = [tuple(f["gps"]) for f in frames]
    rec = [tuple(f["recovered_gps"]) for f in frames]
    resid = [f["residual_m"] for f in frames]
    R.report_html(rundir, sub, tuple(m["center"]), gps, rec, resid, m["stats"])
    print("regenerated", os.path.join(rundir, "report.html"))

if __name__ == "__main__":
    for d in sys.argv[1:]:
        regen(d)
