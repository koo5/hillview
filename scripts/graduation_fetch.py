#!/usr/bin/env python3
"""Fetch the current graduation package from the enrichment workbench and put
it where hillview's API picks it up — the incoming dir — so it can be
previewed and applied in /admin/graduation without going through a browser
download and a copy.

    scripts/graduation_fetch.py                    # everything pending → backend/data/graduation/incoming/
    scripts/graduation_fetch.py --dry-run          # fetch + summarise, write nothing
    scripts/graduation_fetch.py --photo 17eaaceb-… # only that photo's overlay (+ all pending annotations)
    scripts/graduation_fetch.py --no-annotations   # overlays only
    scripts/graduation_fetch.py --container hillview_api   # docker cp into the container instead of the bind mount

The workbench builds the package (POST /graduation/export: JSON ops manifest +
TriG provenance appendix + base64 depth blobs); this script only moves bytes
and reports what is in them. Nothing is applied — that stays a human click in
/admin/graduation (or POST …/packages/<name>/apply with an admin token).

Defaults follow the dev compose: workbench API on 127.0.0.1:8070, incoming
dir = <repo>/backend/data/graduation/incoming (bind-mounted to /app/data in
the api container; GRADUATION_INCOMING_DIR overrides inside the container).
Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_WB = os.environ.get("HV_WORKBENCH_API", "http://127.0.0.1:8070/api")
DEFAULT_DEST = REPO / "backend" / "data" / "graduation" / "incoming"
CONTAINER_DIR = "/app/data/graduation/incoming"
# mirrors overlay_export.DEFAULT_MAX_VISIBILITY_KM
DEFAULT_MAX_VISIBILITY_KM = 150.0


def fetch_package(base: str, photo_ids: list[str] | None, annotation_ids: list[str] | None,
                  note: str | None) -> dict:
    body: dict = {}
    if photo_ids is not None:
        body["photo_ids"] = photo_ids
    if annotation_ids is not None:
        body["annotation_ids"] = annotation_ids
    if note:
        body["note"] = note
    req = urllib.request.Request(f"{base.rstrip('/')}/graduation/export",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def package_name(pkg: dict) -> str:
    """Same name the workbench UI's download button uses."""
    stamp = (pkg.get("created_at") or "")[:19].replace(":", "-").replace("T", "-")
    return f"{pkg.get('package', 'hillview-enrichment')}-{stamp}.json"


def _reach(ov: dict) -> str:
    """How far the labels reach, and — when the fit asked for more — that the
    render's own range is what capped it (the export bakes to
    min(max_visibility_km, render range), so a curator who types 150 into the
    bench's `max` and renders to 100 km gets 100 and deserves to be told)."""
    got = ov.get("labels_cutoff_km")
    if got is None:
        return ""
    asked = (ov.get("fit") or {}).get("max_visibility_km")
    rng = (ov.get("render") or {}).get("max_distance_m")
    note = ""
    if rng is not None and abs(got - rng / 1000) < 0.05:
        wanted = asked if asked is not None else DEFAULT_MAX_VISIBILITY_KM
        if wanted > got + 0.05:
            note = f" (fit asks {wanted:g}, capped by the render's {rng / 1000:g} km)"
    return f" labels→{got} km{note}"


def summarise(pkg: dict, raw_len: int) -> list[str]:
    ops = pkg.get("ops") or []
    lines = [f"package: {pkg.get('package')}  created_at: {pkg.get('created_at')}  "
             f"ops: {len(ops)}  size: {raw_len / 1024:.0f} KB"]
    by_op = Counter(o.get("op") for o in ops)
    lines.append("  ops by type: " + (", ".join(f"{k}×{v}" for k, v in sorted(by_op.items())) or "none"))
    for o in ops:
        if o.get("op") == "set_terrain_overlay":
            ov = o.get("overlay") or {}
            labels = ov.get("labels") or []
            cls = Counter(l.get("class", "?") for l in labels)
            fit = ov.get("fit") or {}
            extras = [k for k in ("hwarp", "hscale", "knots") if fit.get(k)]
            lines.append(
                f"  overlay {str(o.get('photo_id'))[:8]}: render {str((ov.get('render') or {}).get('id'))[:8]}, "
                f"{len(ov.get('skyline', {}).get('elev_deg') or [])} skyline samples, {len(labels)} labels "
                f"({', '.join(f'{k} {v}' for k, v in sorted(cls.items()))}), fit {fit.get('projection')} "
                f"fov {fit.get('fov_deg')} vis {fit.get('visibility_km')}{_reach(ov)}"
                + (f" [{'/'.join(extras)}]" if extras else "")
                + (f", depth blob {str((ov.get('depth') or {}).get('blob'))[:12]}…" if (ov.get('depth') or {}).get('blob') else ", no depth"))
    blobs = pkg.get("blobs") or {}
    if blobs:
        total = sum(len(v.get("data", "")) if isinstance(v, dict) else len(v) for v in blobs.values())
        lines.append(f"  blobs: {len(blobs)} (base64 total {total / 1024:.0f} KB)")
    if pkg.get("skipped"):
        lines.append(f"  skipped: {pkg['skipped']}")
    if pkg.get("provenance_trig") or pkg.get("provenance"):
        lines.append("  provenance appendix: present")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workbench", default=DEFAULT_WB, help=f"workbench API base (default {DEFAULT_WB})")
    ap.add_argument("--photo", action="append", default=None, metavar="ID",
                    help="only this photo's overlay (repeatable); default: every pending overlay")
    ap.add_argument("--annotation", action="append", default=None, metavar="ID",
                    help="only this annotation (repeatable); default: every pending annotation op")
    ap.add_argument("--no-overlays", action="store_true", help="annotations only")
    ap.add_argument("--no-annotations", action="store_true", help="overlays only")
    ap.add_argument("--note", default=None, help="note stored on the workbench's export run")
    ap.add_argument("--dest", type=Path, default=None, help=f"directory to write into (default {DEFAULT_DEST})")
    ap.add_argument("--container", default=None, metavar="NAME",
                    help=f"docker cp into this container's {CONTAINER_DIR} instead of writing to --dest")
    ap.add_argument("--name", default=None, help="file name (default: like the workbench download)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing file of the same name")
    ap.add_argument("--allow-empty", action="store_true", help="write a package even when it has no ops")
    ap.add_argument("--dry-run", action="store_true", help="fetch and summarise, write nothing")
    a = ap.parse_args()

    photo_ids = [] if a.no_overlays else a.photo
    annotation_ids = [] if a.no_annotations else a.annotation
    try:
        pkg = fetch_package(a.workbench, photo_ids, annotation_ids, a.note)
    except urllib.error.HTTPError as e:
        print(f"export failed: HTTP {e.code} {e.read().decode(errors='replace')[:300]}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, OSError) as e:
        print(f"export failed: cannot reach {a.workbench}: {e}", file=sys.stderr)
        return 2
    raw = json.dumps(pkg, ensure_ascii=False, indent=2).encode()
    for line in summarise(pkg, len(raw)):
        print(line)
    if not (pkg.get("ops") or []) and not a.allow_empty:
        print("nothing pending — no package written (use --allow-empty to write it anyway)")
        return 0
    if a.dry_run:
        print("dry run — not written")
        return 0
    name = a.name or package_name(pkg)
    if not name.endswith(".json"):
        name += ".json"
    # a package is a snapshot of the moment; older ones in the incoming dir are
    # not "pending work", they are stale duplicates the admin UI would offer
    # alongside this one
    if not a.container and not a.dest:
        for old in sorted((a.dest or DEFAULT_DEST).glob(f"{pkg.get('package', 'hillview-enrichment')}-*.json")):
            if old.name != name:
                print(f"  (superseded, removing: {old.name})")
                old.unlink()
    if a.container:
        # stage in the repo's scratch and copy in: works even when the container's
        # data dir is a named volume rather than the dev bind mount
        tmp = REPO / "backend" / "data" / "graduation" / ".staging"
        tmp.mkdir(parents=True, exist_ok=True)
        f = tmp / name
        f.write_bytes(raw)
        subprocess.run(["docker", "exec", a.container, "mkdir", "-p", CONTAINER_DIR], check=True)
        if not a.force:
            probe = subprocess.run(["docker", "exec", a.container, "test", "-e", f"{CONTAINER_DIR}/{name}"])
            if probe.returncode == 0:
                print(f"refusing to overwrite {a.container}:{CONTAINER_DIR}/{name} (use --force)", file=sys.stderr)
                return 3
        subprocess.run(["docker", "cp", str(f), f"{a.container}:{CONTAINER_DIR}/{name}"], check=True)
        f.unlink()
        where = f"{a.container}:{CONTAINER_DIR}/{name}"
    else:
        dest = a.dest or DEFAULT_DEST
        dest.mkdir(parents=True, exist_ok=True)
        f = dest / name
        if f.exists() and not a.force:
            print(f"refusing to overwrite {f} (use --force)", file=sys.stderr)
            return 3
        f.write_bytes(raw)
        where = str(f)
    print(f"written: {where}")
    print("next: hillview /admin/graduation lists it for preview → apply "
          f"(API: GET /api/admin/graduation/packages/{name} with an admin token)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
