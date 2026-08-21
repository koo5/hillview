#!/usr/bin/env python3
"""One-shot: prefix existing terrain depth artifacts with the HVD1 header.

Since 2026-08-20 the renderer emits a self-identifying depth buffer (see
`enrich/terrain/renderer.py` — magic, version, header length, grid, sample
scale). Artifacts rendered before that are bare samples. Rather than teach
every reader to accept both forever, or re-render 800 MB of panoramas, this
walks the artifacts once and puts the header on.

Runs INSIDE the workbench API container, where /artifacts is mounted:

    docker exec -i enrich_api python - < scripts/terrain_migrate_depth_header.py            # dry run
    docker exec -i enrich_api python - < scripts/terrain_migrate_depth_header.py --apply

Grid and sample scale come from each render's meta (the API's own listing),
never guessed from the file size. Writes are atomic (temp + rename) and the
pre-compressed `.gz` sibling is regenerated to match. Idempotent: a buffer
that already carries the header is skipped.
"""
import gzip
import json
import os
import struct
import sys
import tempfile
import urllib.request

MAGIC = b"HVD1"
VERSION = 1
HEADER_BYTES = 32
ARTIFACTS = os.environ.get("ARTIFACTS_DIR", "/artifacts")
API = os.environ.get("WB_API", "http://localhost:8070/api")


def renders():
    with urllib.request.urlopen(f"{API}/terrain/renders?limit=1000", timeout=60) as r:
        return json.load(r)["renders"]


def main() -> int:
    apply = "--apply" in sys.argv
    done = skipped = migrated = failed = 0
    for row in renders():
        meta, rel = row.get("meta") or {}, None
        # the listing does not carry depth_path; artifacts are <id>.depth.bin
        rel = os.path.join("terrain", f"{row['id']}.depth.bin")
        path = os.path.join(ARTIFACTS, rel)
        if not os.path.exists(path):
            continue
        done += 1
        w, h = meta.get("width"), meta.get("height")
        scale = float(meta.get("depth_scale_m") or 4.0)
        with open(path, "rb") as f:
            head = f.read(16)
        size = os.path.getsize(path)
        if head[:4] == MAGIC:
            skipped += 1
            continue
        if not w or not h:
            print(f"  !! {row['id'][:8]}: meta has no grid ({size} bytes) — skipped")
            failed += 1
            continue
        if size != w * h * 2:
            print(f"  !! {row['id'][:8]}: {size} bytes but meta says {w}×{h} "
                  f"({w * h * 2}) — skipped, look at it by hand")
            failed += 1
            continue
        print(f"  {row['id'][:8]}: {w}×{h}, {size / 1048576:.1f} MB"
              + ("" if apply else "  (dry run)"))
        if not apply:
            migrated += 1
            continue
        header = (MAGIC + struct.pack("<HHIIf", VERSION, HEADER_BYTES, w, h, scale)
                  ).ljust(HEADER_BYTES, b"\0")
        with open(path, "rb") as f:
            body = f.read()
        d = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "wb") as f:
            f.write(header)
            f.write(body)
        os.replace(tmp, path)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "wb") as f:
            f.write(gzip.compress(header + body, compresslevel=6))
        os.replace(tmp, path + ".gz")
        migrated += 1
    print(f"\n{done} artifacts: {migrated} {'migrated' if apply else 'to migrate'}, "
          f"{skipped} already had the header, {failed} left alone")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
