# Panorama source archaeology — field notes

Status: **reference / findings** · captured 2026-06-15 · companion to
[`vision-subsystem.md`](vision-subsystem.md) (see its Appendix B) and the tools in
`scripts/enrich/`.

> **Why this exists.** The vision/enrichment subsystem needs, for each delivered Hillview
> panorama, its upstream `pics` source — the stitch `.pto` (per-frame camera poses + projection)
> and ideally the stitched `.exr` (pixels). Those let us map a pano annotation rectangle back to a
> clean source frame (`pto-map`, design-doc App. B) and calibrate bearings. Establishing that
> delivered-pano → source link turned into a multi-session dig because the source data is scattered
> across **five pipeline generations** with incompatible layouts and naming. This is the map of that
> terrain so we don't re-derive it. **We don't expect to revisit for a while.**

## TL;DR

- **19 annotated ("gold") panos. 18/19 have recoverable poses, 11/19 have stitched pixels, 1
  (Zbraslav) is CR2-frames-only.** The per-pano table lives in `scripts/enrich/pano_map.md`
  (regenerable). 53 delivered panos total; 35 are 0-annotation (30 of them also sourced).
- The robust join key across all generations is **crop-dims**: a `.pto`'s `p`-line
  `S<l>,<r>,<t>,<b>` gives the delivered image size `(r−l)×(b−t)`, matched to the photo's
  `width×height`. Frame-code tokens in `original_filename` and `uploaded/prod` manifest `photo_id`s
  are the other two keys.
- **Projection and FOV vary per pano** — `f0` rectilinear, `f1` cylindrical, `f2` equirectangular;
  FOV 26°–360°. Never assume; read the `p`-line.

## Where the data lives

- **Delivered panos + annotations:** the prod DB export in `~/hggg/` — `photos_*.csv`,
  `photo_annotations_*.csv` (dump naming gains a `_N` suffix; the tools glob `photos*.csv` and take
  the newest). Key columns: `id`, `original_filename`, `width`, `height`, `geometry` (EWKB hex or
  WKT point), `compass_angle`, `description`, `analysis`.
- **Source data:** the `/shared/autocopy/` mount, three top-level trees:
  - `autocopy_done/` — recent finished shoots (current pipeline).
  - `autocopy_todo_review/` — unprocessed / half-stitched shoots, plus `final-backup/`,
    `oldpanos/`, and dated dirs like `2026-03-28_zbraslav`.
  - `hillview_eos/` — `done/` (finished, incl. old-pipeline), `0ver/` ("old version" pipelines),
    and **`hugin/`** (hand-stitched Hugin projects, organized by location).

## The five pipeline generations (how to recognise each)

| gen | layout | delivered crop lives in | examples |
| --- | --- | --- | --- |
| **1 (current)** | `panoN/phase_03_pto_gen … 09_pto_canvas / 10_warps / 11_exr_blend / 12_exr_render / 13_pyramid`; `render/*.exr` + `*.exr.meta.json`; `uploaded/{dev,dev2,prod}/*.json` manifests | `phase_09_pto_canvas/pano.pto` (`S` line) | grebovka, kozi-hrbety, 2026-05-05-melnik, 2026-05-25, Havránka |
| **2** | `pano/<range>/…` or `panoN/work/phase_03_pto … 06_optimize / 07_stitch / 08_render` | **`phase_07_stitch/pano.pto`** (optimize-phase crop is *different/bigger*) | prumyslovka-0ver, 2026-04-23-melnik-0ver |
| **3** | `panoN/phase_03_pto … 06_optimize / render/` with the **EXR cleaned** (only `*.exr.meta.json` left); **re-crops at render** | *no pto holds the delivered crop* → pose only via manifest→workdir link | karlin_vysehrad_branik |
| **4 (oldest)** | `span<N>/p_<first>-<last>-NN.pto` (+ nested `cr2/`, the newer copy), `p_*_hdr.exr` | the `p_*.pto` `S` line | prosek_tresnovka_zizkaperk, 2026-04-07, panenske-brezany |
| **hand-Hugin** | `hillview_eos/hugin/<location>/…/<idx>_<code> - <idx>_<code>.pto` (codes like `36A7584`, *no* leading 0); some `<code> - <code>.pto` | the `.pto` `S` line | prosek/vychod1, boranovice, silvestr, letnany, dablicak1, cakovice, … |

## Join keys (in order of authority)

1. **`uploaded/prod/*.json` manifest** → `{filename, photo_id, status}`. Authoritative but only on
   recent (gen-1/3) shoots. Per-environment: `dev`/`dev2`/`prod` each have *different* photo_ids;
   **only `prod` matches the prod dump.**
2. **Frame-code tokens** shared between `original_filename` and a `.pto`/`.exr` filename. Codes look
   like `036A0457`, `AAAA3089`, `AAAB7011`, `36A7584`. Regex used: `[0-9A-Z]{2,4}\d{3,4}`. Fails when
   `original_filename` is junk (e.g. `00.tiff`).
3. **Crop-dims** — `.pto` `p`-line `S<l>,<r>,<t>,<b>` → `(r−l)×(b−t)` vs photo `width×height`. The
   most generation-robust key; the *only* one for hand-Hugin panos with lost names. **Gotcha:** the
   pto phase that carries the delivered crop differs by generation (table above) — so index *every*
   `pano.pto`, not just the `*_canvas` one (this was a real bug: Mělník `44e15a3f` matched only once
   we read `phase_07_stitch/pano.pto`).

## Gotchas worth remembering

- **Projection varies** (f0/f1/f2) and **manual bend/straighten/crop** happens — the canvas/stitch
  `.pto` describes the delivered pixels *including* manual tweaks, **except gen-3** which re-crops at
  render (no pto has the delivered crop there).
- **`pano_trafo`** (ships with Hugin) inverts a panorama pixel → source-frame pixel given a `.pto`,
  across any projection — use it rather than hand-rolling lens math (design-doc App. B).
- **Per-frame `.CR2.geo.xmp`** (lat/lon/bearing) lives in the *source date dir*, not the pano
  bucket; join by CR2 stem. Bearing is phone-magnetometer — biased (the core problem the calibration
  work addresses).
- Hillview also stores the **individual source frames** as separate photos (`036A0479.webp` …),
  8688×5792 — useful as Track-B corpus.
- `original_filename` can be lossy (`00.tiff`, `036A9261 - 036A9270.tif` with spaces) → dims-join.
- Same span can map to **several** photo_ids (re-uploads); pick the annotated one. Same workdir can
  have **re-stitched duplicates** with drifting dims (flagged `dims✗` by `match_autocopy.py`).
- Pick the **newest `.pto`** when duplicates exist (e.g. `span1/cr2/…` over `span1/…`).

## The toolkit (`scripts/enrich/`)

- **`pano_map.py` → `pano_map.md`** — the canonical map. Joins every delivered pano to its
  `.pto`/`.exr` by frame-code token *and* crop-dims; catalogs the `hugin/` tree; lists untapped
  pano/span workdirs. Regenerate: `python scripts/enrich/pano_map.py` (reads all `pano.pto`/`p_*`
  p-lines across the mount — ~2 min).
- **`match_autocopy.py`** — diagnostic matcher (workdir-centric): `uploaded/prod` manifest →
  `original_filename` → fuzzy dims+geo; flags re-stitch/version drift (`dims✗`). Reusable
  `analyze()`.
- **`r2_select_and_gate.py`** — unrelated to the hunt (M1-0 feasibility probe).
- Data dep: `--data ~/hggg` (default). **Note:** these run sandboxed to the repo, so they write
  their `.md` outputs *inside the repo only* — copy elsewhere manually if needed.

## Results snapshot (2026-06-15, `photos_1.csv`)

Headline annotated panos and their sources (full table in `pano_map.md`):

| pano | annos | source |
| --- | --: | --- |
| `333e8851` | 88 | hand-Hugin `hugin/100EOS5D/prosek/…/vychod1/00_36A7584 - 18_36A7566.pto` (f0; crop→66897×5133 ✓) |
| `6ed01a83` | 83 | gen-4 prosek `span1/cr2/p_036A0457-036A0467-11.pto` |
| `f4b4d58c` | 80 | gen-1 Havránka `pano1` — pto + `.exr` |
| `17eaaceb` / `76ee2f03` | 43 / 20 | gen-4 `0ver/2026-04-07/span7,span8` (Ďáblice) |
| `44e15a3f` | 38 | gen-2 melnik-0ver `pano1/work/phase_07_stitch/pano.pto` + `.exr` |
| `de06ceaa` / `c8ba08a5` | 11 / 1 | hand-Hugin `hugin/boranovice/` |

**Holdouts / open items for next time:**
- `575223fd` (Zbraslav, 10 annos) — **no `.pto` present**; only the `AAAA1025…1035` CR2 frames in
  `autocopy_todo_review/2026-03-28_zbraslav/1/`. Find the Hugin project or re-stitch.
- `6d62ad56` (Vyšehrad, 9) — pose exists (`karlin/pano4/phase_06_optimize/pano.pto`) but only
  reachable via the prod-manifest→workdir link, which `pano_map.py` doesn't fold in (gen-3 re-crop +
  token-less name). `match_autocopy.py` has the link.
- **Lots of unstitched stock:** 27 untapped pano/span workdirs + the `0ver/` and `hugin/` trees hold
  many 0-annotation panos with poses — future annotation targets and Track-B corpus.
- **Re-run after each fresh prod dump or autocopy reorg** (the trees and naming keep evolving).
- Ongoing (owner): collecting older raw/`.pto` data from pre-pipeline eras into the mount.
