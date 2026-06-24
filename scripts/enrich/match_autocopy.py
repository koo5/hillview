#!/usr/bin/env python3
"""
Match pics pano workdirs in /shared/autocopy against delivered panos in the
Hillview CSV export, so each delivered pano can be linked to its .pto.

Tiered matching (autocopy is messy; naming/upload conventions are recent):
  1. prod-manifest : uploaded/prod/*.json gives frame-range filename -> prod photo_id
  2. filename      : pano render basename appears in a photo's original_filename
  3. fuzzy         : exact canvas-crop dims (+ geo proximity) for older panos

`analyze()` is the reusable entry point (also used by pano_inventory.py).
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

P_RE = re.compile(r'^p .*?\bf(\d+)\b.*?\bw(\d+)\b.*?\bh(\d+)\b.*?\bv([\d.]+)\b')
S_RE = re.compile(r'\bS(\d+),(\d+),(\d+),(\d+)\b')


def parse_point(g):
    if not g:
        return None
    g = g.strip()
    if g.upper().startswith("POINT"):
        try:
            lon, lat = g[g.index("(") + 1:g.index(")")].split()
            return float(lon), float(lat)
        except Exception:
            return None
    try:
        if g.lower().startswith("0101000020"):
            b = bytes.fromhex(g)
            return struct.unpack_from("<d", b, 9)[0], struct.unpack_from("<d", b, 17)[0]
    except Exception:
        pass
    return None


def haversine_m(a, b):
    R = 6371000.0
    (lo1, la1), (lo2, la2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def parse_canvas_pto(path):
    f = v = crop = None
    try:
        with open(path) as fh:
            for line in fh:
                if line.startswith("p "):
                    m = P_RE.match(line)
                    if m:
                        f, _, _, v = int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))
                    s = S_RE.search(line)
                    if s:
                        l, r, t, b = map(int, s.groups())
                        crop = (r - l, b - t)
                    break
    except Exception:
        pass
    return {"proj": f, "fov": v, "crop": crop}


def scan(root):
    """One pruned walk. Returns (canvas_pto_paths, prod_json_paths, pano_dirs).

    pano_dirs: list of (path, state) where state in {canvas, partial, raw}.
    Prunes the heavy `*_files` tile subtrees.
    """
    canvas, prod, panos = [], [], []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.endswith("_files") and d not in ("opt", "mov", ".git")]
        base = os.path.basename(dirpath)
        parts = dirpath.split(os.sep)
        if base.startswith("phase_") and base.endswith("_pto_canvas") and "pano.pto" in files:
            canvas.append(os.path.join(dirpath, "pano.pto"))
        if base == "prod" and os.path.basename(os.path.dirname(dirpath)) == "uploaded":
            prod += [os.path.join(dirpath, f) for f in files if f.endswith(".json")]
        if base.startswith("pano") and "uploaded" not in parts:
            has_canvas = any(d.startswith("phase_") and d.endswith("_pto_canvas") for d in dirs)
            has_phase = any(d.startswith("phase_") for d in dirs)
            panos.append((dirpath, "canvas" if has_canvas else "partial" if has_phase else "raw"))
    return sorted(canvas), prod, panos


def collect_prod_manifests(json_paths):
    m = {}
    for p in json_paths:
        try:
            for e in json.load(open(p)):
                fn = e.get("filename")
                if fn:
                    m[fn] = (e.get("photo_id"), e.get("status"))
        except Exception:
            pass
    return m


def render_basename(wd):
    for sub in ("phase_*_exr_render/*.exr", "render/*.exr"):
        g = glob.glob(os.path.join(wd, sub))
        if g:
            return os.path.basename(g[0])[:-4]
    return None


def geom_pto(wd):
    """Best geometry pto in a workdir: canvas (has crop) for new-pipeline dirs,
    else the newest optimize/baseline pto for old-pipeline dirs (no canvas phase)."""
    g = sorted(glob.glob(os.path.join(wd, "phase_*_pto_canvas/pano.pto")))
    if g:
        return g[-1]
    for pat in ("phase_*optimize/pano.pto", "phase_*baseline/pano.pto", "phase_*pto*/pano.pto"):
        g = sorted(glob.glob(os.path.join(wd, pat)))
        if g:
            return g[-1]
    return None


def read_meta(wd):
    for sub in ("phase_*_exr_render/*.exr.meta.json", "render/*.exr.meta.json"):
        g = glob.glob(os.path.join(wd, sub))
        if g:
            try:
                return json.load(open(g[0]))
            except Exception:
                return None
    return None


def find_csv(data, prefix):
    hits = sorted(glob.glob(os.path.join(data, prefix + "*.csv")))
    if not hits:
        raise FileNotFoundError(f"no {prefix}*.csv in {data}")
    return hits[-1]  # tolerate photos.csv / photos_1.csv dump naming


def analyze(autocopy, data):
    anno = defaultdict(int)
    with open(find_csv(data, "photo_annotations")) as f:
        for r in csv.DictReader(f):
            if r.get("is_current") in ("t", "true", "True", "1"):
                anno[r["photo_id"]] += 1

    by_id, by_ofstem, dims_index = {}, defaultdict(list), defaultdict(list)
    with open(find_csv(data, "photos")) as f:
        for r in csv.DictReader(f):
            try:
                w, h = int(r["width"]), int(r["height"])
            except Exception:
                w = h = 0
            row = {"id": r["id"], "of": r.get("original_filename") or "", "w": w, "h": h,
                   "ll": parse_point(r.get("geometry")), "comp": r.get("compass_angle"),
                   "desc": r.get("description") or ""}
            by_id[r["id"]] = row
            stem = os.path.splitext(row["of"])[0]
            if stem:
                by_ofstem[stem].append(row)
            if w and h:
                dims_index[(w, h)].append(row)

    canvas_ptos, prod_jsons, panodirs = scan(autocopy)
    prod = collect_prod_manifests(prod_jsons)

    rows = []
    for wd, state in panodirs:
        rb = render_basename(wd)
        if state != "canvas" and rb is None:
            continue  # raw/partial with no render = untapped source, not a delivered pano
        gp = geom_pto(wd)
        cv = parse_canvas_pto(gp) if gp else {"proj": None, "fov": None, "crop": None}
        meta = read_meta(wd) or {}
        match = method = None
        note = ""
        if rb and f"{rb}.exr" in prod:
            pid, status = prod[f"{rb}.exr"]
            if pid and pid in by_id:
                match, method = by_id[pid], "prod-manifest"
            else:
                method, note = "prod-manifest", f"pid={pid} status={status} not in export"
        if match is None and rb and rb in by_ofstem:
            match, method = by_ofstem[rb][0], "filename"
        if match is None and cv["crop"] and cv["crop"] in dims_index:
            cands = dims_index[cv["crop"]]
            if meta.get("latitude"):
                mp = (meta["longitude"], meta["latitude"])
                cands = sorted([c for c in cands if c["ll"]], key=lambda c: haversine_m(mp, c["ll"]))
            if cands:
                match, method = cands[0], "dims" + ("+geo" if meta.get("latitude") else "")
        agree = ""
        if match and cv["crop"]:
            agree = "ok" if (match["w"], match["h"]) == cv["crop"] else f"dims✗({match['w']}x{match['h']} vs {cv['crop'][0]}x{cv['crop'][1]})"
        rows.append({"wd": wd.replace(autocopy, "").lstrip("/"), "wd_abs": wd, "state": state,
                     "frames": rb, "cv": cv, "meta": meta, "match": match,
                     "method": method or "-", "agree": agree, "note": note,
                     "annos": anno.get(match["id"], 0) if match else 0})

    return {"rows": rows, "by_id": by_id, "anno": anno, "panodirs": panodirs, "n_prod": len(prod)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--autocopy", default="/shared/autocopy")
    ap.add_argument("--data", default=os.path.expanduser("~/hggg"))
    args = ap.parse_args()
    R = analyze(args.autocopy, args.data)
    rows = R["rows"]
    print(f"pano workdirs(canvas): {len(rows)}   prod-manifest entries: {R['n_prod']}\n")
    for r in sorted(rows, key=lambda r: (-r["annos"], r["wd"])):
        cv = r["cv"]
        pf = f"f{cv['proj']}/{cv['fov']:.0f}" if cv["proj"] is not None else "-"
        cw = f"{cv['crop'][0]}x{cv['crop'][1]}" if cv["crop"] else "-"
        pid = r["match"]["id"][:8] if r["match"] else "(none)"
        ok = "✓" if r["agree"] == "ok" else ("?" if not r["agree"] else "✗")
        print(f"{r['wd'][:50]:50} {pf:9} {cw:>13} {r['method']:13} {pid:10} {r['annos']:>4} {ok:>3}")
        if r["note"]:
            print(f"    ! {r['note']}")
        if r["agree"].startswith("dims✗"):
            print(f"    ! {r['agree']}")
    gold = [r for r in rows if r["match"] and r["annos"] > 0]
    print(f"\nlinked gold: {len(gold)} -> "
          + ", ".join(f"{r['match']['id'][:8]}({r['annos']})" for r in sorted(gold, key=lambda r: -r["annos"])))


if __name__ == "__main__":
    main()
