#!/usr/bin/env python3
"""
Comprehensive pano source map -> writes /shared/autocopy/PANO_MAP.md (and a repo copy).

Joins every delivered Hillview pano to its pics source by BOTH:
  - frame-code tokens shared with original_filename (036A0457, AAAA3089, 36A7584), and
  - exact crop-dims from a .pto p-line `S<l>,<r>,<t>,<b>` -> (r-l)x(b-t),
so even hand-Hugin panos with useless names (00.tiff) resolve. Also catalogs the
hillview_eos/hugin/ hand-stitch tree and the untapped raw/partial workdirs.
"""
import csv, glob, os, re, sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
A = "/shared/autocopy"
DATA = os.path.expanduser("~/hggg")
TOK = re.compile(r'[0-9A-Z]{2,4}\d{3,4}')
FWH = re.compile(r'\bf(\d+)\b.*?\bw(\d+)\b.*?\bh(\d+)\b.*?\bv([\d.]+)')
SRE = re.compile(r'\bS(\d+),(\d+),(\d+),(\d+)\b')


def fc(pre):
    return sorted(glob.glob(os.path.join(DATA, pre + "*.csv")))[-1]


def toks(s):
    return set(TOK.findall(s or ""))


def pto_pline(path):
    """(proj, fov, crop_dims) from the first `p ` line; crop = (r-l, b-t) or None."""
    try:
        with open(path, errors="ignore") as f:
            for line in f:
                if line.startswith("p "):
                    m, s = FWH.search(line), SRE.search(line)
                    proj = int(m.group(1)) if m else None
                    fov = float(m.group(4)) if m else None
                    crop = None
                    if s:
                        l, r, t, b = map(int, s.groups())
                        crop = (r - l, b - t)
                    return proj, fov, crop
                if line.startswith("i "):
                    break
    except OSError:
        pass
    return None, None, None


def want_pto(path):
    # Read every geometry pto: `pano.pto` in any phase dir (gen-2/3 put the final
    # crop in phase_07_stitch / phase_08_render, not *_canvas), all `p_*` (gen-4),
    # and anything in the hand-Hugin tree. The crop-dims join picks the one whose
    # S-line crop equals the delivered dims.
    base = os.path.basename(path)
    return base == "pano.pto" or base.startswith("p_") or os.sep + "hugin" + os.sep in path


def main():
    anno = defaultdict(int)
    for r in csv.DictReader(open(fc("photo_annotations"))):
        if r.get("is_current") in ("t", "true", "True", "1"):
            anno[r["photo_id"]] += 1

    panos = []
    for r in csv.DictReader(open(fc("photos"))):
        try:
            w, h = int(r["width"]), int(r["height"])
        except Exception:
            w = h = 0
        of = r.get("original_filename") or ""
        ar = (max(w, h) / min(w, h)) if w and h else 0
        if not (ar >= 2.0 or "---" in of or of.lower().startswith("p_") or w >= 15000):
            continue
        panos.append({"id": r["id"], "of": of, "w": w, "h": h, "toks": toks(of),
                      "annos": anno.get(r["id"], 0), "desc": (r.get("description") or "").strip()})

    pto_tok = defaultdict(list)
    pto_dim = defaultdict(list)
    exr_tok = defaultdict(list)
    hugin = []
    untapped = []
    for dp, dirs, files in os.walk(A):
        dirs[:] = [d for d in dirs if not d.endswith("_files")
                   and d not in ("opt", "mov", ".git", ".thumbnails")]
        base = os.path.basename(dp)
        if (base.startswith("pano") or base.startswith("span")) and "uploaded" not in dp.split(os.sep):
            has_render = any(f.lower().endswith((".exr", ".exr.meta.json")) for f in files) \
                or any(d == "render" or d.endswith("_exr_render") for d in dirs)
            if not has_render:
                cr2 = sum(1 for f in files if f.lower().endswith(".cr2"))
                untapped.append((dp, "partial" if any(d.startswith("phase_") for d in dirs) else "raw", cr2))
        for fn in files:
            low = fn.lower()
            p = os.path.join(dp, fn)
            if low.endswith(".pto") and want_pto(p):
                proj, fov, crop = pto_pline(p)
                for t in toks(fn):
                    pto_tok[t].append(p)
                if crop:
                    pto_dim[crop].append(p)
                if os.sep + "hugin" + os.sep in p:
                    hugin.append((p, proj, fov, crop))
            elif low.endswith(".exr") or low.endswith(".exr.meta.json"):
                kind = "meta" if low.endswith(".meta.json") else "exr"
                for t in toks(fn):
                    exr_tok[t].append((p, kind))

    mt = lambda p: (os.path.getmtime(p) if os.path.exists(p) else 0)
    rel = lambda p: p.replace(A, "").lstrip("/") if p else "—"

    for pano in panos:
        ct = set()
        for t in pano["toks"]:
            ct |= set(pto_tok.get(t, []))
        strong = [p for p in ct if pano["toks"] and toks(os.path.basename(p)) >= pano["toks"]]
        dimp = pto_dim.get((pano["w"], pano["h"]), [])
        pset = strong or dimp
        pano["pto"] = max(pset, key=mt) if pset else None
        pano["pto_how"] = "token" if strong else ("dims" if dimp else "—")
        ce = {}
        for t in pano["toks"]:
            for (p, kind) in exr_tok.get(t, []):
                if toks(os.path.basename(p)) >= pano["toks"]:
                    ce[p] = kind
        exrs = [p for p, k in ce.items() if k == "exr"]
        metas = [p for p, k in ce.items() if k == "meta"]
        pano["exr"] = max(exrs, key=mt) if exrs else None
        pano["meta"] = max(metas, key=mt) if metas else None

    panos.sort(key=lambda p: (-p["annos"], -max(p["w"], p["h"])))

    L = ["# Pano source map (auto-generated)\n",
         f"_`{os.path.basename(fc('photos'))}` × `{A}` · regenerate: "
         "`python scripts/enrich/pano_map.py`_\n",
         "Join = frame-code token (in `original_filename`) OR exact crop-dims "
         "(`.pto` `S` line → delivered dims). Pixels via `.exr` (`.meta` only = EXR cleaned).\n",
         "## Annotated panos\n",
         "| pano | annos | dims | desc | poses (.pto) | how | pixels |",
         "|---|--:|---|---|---|---|---|"]
    n = npto = npix = 0
    for p in panos:
        if not p["annos"]:
            continue
        n += 1
        npto += bool(p["pto"])
        npix += bool(p["exr"])
        pix = rel(p["exr"]) if p["exr"] else (f"meta: {rel(p['meta'])}" if p["meta"] else "—")
        L.append(f"| `{p['id'][:8]}` | {p['annos']} | {p['w']}x{p['h']} | {p['desc'][:42]} | "
                 f"{rel(p['pto'])} | {p['pto_how']} | {pix} |")

    L += ["\n## Delivered panos with 0 annotations (sources still useful as corpus)\n",
          "| pano | dims | poses (.pto) | pixels |", "|---|---|---|---|"]
    n0 = n0src = 0
    for p in panos:
        if p["annos"]:
            continue
        n0 += 1
        if p["pto"] or p["exr"]:
            n0src += 1
        L.append(f"| `{p['id'][:8]}` | {p['w']}x{p['h']} | {rel(p['pto'])} | "
                 f"{rel(p['exr']) if p['exr'] else '—'} |")

    L += ["\n## hillview_eos/hugin/ hand-stitch catalog\n",
          "| project (.pto) | proj | fov | crop-dims |", "|---|---|---|---|"]
    for p, proj, fov, crop in sorted(hugin):
        cd = f"{crop[0]}x{crop[1]}" if crop else "—"
        pj = f"f{proj}" if proj is not None else "f?"
        fv = int(fov) if fov else "—"
        L.append(f"| {rel(p)} | {pj} | {fv} | {cd} |")

    L += ["\n## Untapped sources (pano/span workdirs with no stitched output yet)\n",
          "| workdir | state | #CR2 |", "|---|---|---:|"]
    for d, st, cr2 in sorted(untapped):
        L.append(f"| {rel(d)} | {st} | {cr2} |")

    L += ["\n## Summary\n",
          f"- annotated panos: **{n}** — with poses **{npto}/{n}**, with pixels **{npix}/{n}**",
          f"- 0-annotation delivered panos: **{n0}** — with a source **{n0src}/{n0}**",
          f"- hugin hand-stitch projects catalogued: **{len(hugin)}**",
          f"- untapped pano/span workdirs (no stitched output): **{len(untapped)}**"]
    out = "\n".join(L) + "\n"
    dest = os.path.join(os.path.dirname(__file__), "pano_map.md")
    open(dest, "w").write(out)
    print(f"[written {dest}]  ({n} annotated, {npto} with poses, {npix} with pixels)")


if __name__ == "__main__":
    main()
