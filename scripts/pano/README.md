# Panorama stitching pipeline

Handheld panoramas from CR2 → stitched EXR. Oriented around the assumption
that parallax is everywhere and control-point hygiene is the whole game.

## Dependencies

```bash
flatpak install flathub org.darktable.Darktable
apt install hugin-tools enblend exiftool   # nona, enblend, celeste_standalone,
                                           # autooptimiser, pto_gen, cpfind
```

## Tools in this directory

| Script | Purpose |
|---|---|
| `pto_horizontal_baseline.py` | Reset image yaw/pitch/roll to a horizontal strip |
| `pto_cp_celeste.sh` | Drop sky/cloud CPs via Hugin's celeste SVM |
| `pto_cp_pairwise.py` | Drop CPs between non-adjacent images (pair-gap filter) |
| `pto_cp_topmost.py` | Keep K topmost CPs per (image, side) — dodges bottom-of-frame parallax |
| `pto_optvars.py` | Rewrite the PTO `v` block — which variables the optimizer may touch |
| `pto_stitch_exr.py` | nona + enblend → EXR, keeps warped intermediates on disk |
| `enfuse_bracket.sh` | Fuse a bracketed exposure stack via align_image_stack + enfuse |
| `exr_linearize.py` | Convert a display-referred EXR to scene-linear (inverse sRGB OETF) and retag |
| `exr_sanity.sh` | Report an EXR's pixel range and classify display-referred vs scene-linear |
| `exr_to_webp_pyramid.py` | Convert an EXR (linear or sRGB, reads the encoding tag) to a WebP Deep Zoom tile pyramid |
| `exr_to_instagram_tiles.py` | Resize and center-crop an EXR into up to 10 4:5 JPEG tiles for an Instagram carousel |
| `dz_view.sh` | Serve a DZI pyramid locally with OpenSeadragon for quick inspection |
| `pipeline.py` | End-to-end orchestrator: runs the whole CR2→EXR workflow as resumable, numbered, idempotent phases |
| `xmp_module.py` | Edit a named darktable module across all XMP sidecars (raw-stage utility) |

`pto_cp_celeste.sh` and `pto_cp_pairwise.py` are kept as post-hoc filters
for PTOs generated *without* `cpfind --celeste --linearmatch`. On the happy
path, cpfind does both at generation time; the standalone filters are
fallbacks, not part of the main flow.

## Workflow

CR2s in `$DIR`. Everything ends up under `$DIR/tiff/`.

### RAW develop

Open in darktable GUI, tweak NON-LOCAL modules only (white balance,
filmic/sigmoid, exposure), copy history, apply to all, close.
Then batch to TIFF:

```bash
scripts/raw/raw_darktable.py -j 24 "$DIR"
cd "$DIR/tiff"
```

### Merge bracketed stacks (optional)

If each tripod position was shot with auto-exposure bracketing (e.g. a
3-shot -1EV / 0EV / +1EV stack), fuse each bracket into one display-ready
TIFF before stitching.

**Why not darktable's "Create HDR DNG"**: one-click with no configuration,
poor alignment for handheld brackets, and the output HDR DNG still needs
manual tone mapping.

**What works**: `align_image_stack` (CP-based alignment) + `enfuse`
(exposure fusion — not HDR merge — output is display-ready LDR).

```bash
# For each bracket (e.g. 3 TIFFs from one position):
scripts/pano/enfuse_bracket.sh fused01.tif shot01a.tif shot01b.tif shot01c.tif
# ... repeat per position, producing fused01.tif fused02.tif ...
```

The `fusedNN.tif` files then feed the stitching section as if they were
single-exposure TIFFs.

### Stitching

```bash
# Create Hugin project with CPs. cpfind's built-in filters prevent bad
# matches at generation time rather than removing them after:
#   --linearmatch       only consider adjacent image pairs (no false matches
#                       between distant frames with similar sky/texture)
#   --celeste           skip CPs that fall on sky regions (SVM classifier)
pto_gen *.tif -o pano.pto
cpfind --linearmatch --celeste --celesteThreshold=0.5 -o pano.pto pano.pto

# Drop bottom-of-frame CPs where parallax is worst.
scripts/pano/pto_cp_topmost.py pano.pto --per-side 2 -o s1.pto

# Reset positions to a clean horizontal baseline. Discards whatever the
# Assistant's optimizer drifted to — parallax-poisoned CPs make it lie.
scripts/pano/pto_horizontal_baseline.py s1.pto --overlap 30 -o s2.pto

# Optimize incrementally — unlock yaw first, confirm, then pitch, then roll.
scripts/pano/pto_optvars.py s2.pto --free y -o opt.pto
autooptimiser -n opt.pto -o opt.pto
scripts/pano/pto_optvars.py opt.pto --free y,p -o opt.pto
autooptimiser -n opt.pto -o opt.pto
scripts/pano/pto_optvars.py opt.pto --free y,p,r -o opt.pto
autooptimiser -n opt.pto -o opt.pto

# Level horizon + size the output canvas to source resolution. Needed when
# the PTO came from `pto_gen` (Hugin GUI Assistant sets canvas already).
# Without this, pto_gen's default w3000 caps the final pano at ~1200 px.
pano_modify --straighten --fov=AUTO --canvas=AUTO --crop=AUTO \
    -o opt.pto opt.pto

# Stitch to EXR. Warped intermediates are kept on disk so a failed blend
# doesn't cost the 30+ minute nona step. --no-tag skips the default sRGB
# tag since we're about to convert to linear.
scripts/pano/pto_stitch_exr.py opt.pto --prefix pano --no-tag
# -> pano.exr (plus pano0000.tif .. panoNNNN.tif until you `rm` them)

# Apply inverse sRGB OETF so pano.exr is semantically scene-linear. Tools
# that assume EXR = linear (darktable, Nuke, compositors) render correctly.
# Tags the file as hillview:encoding=linear.
scripts/pano/exr_linearize.py pano.exr
```

### Automated: all of the above

```bash
scripts/pano/pipeline.py --raws-dir "$DIR" --overlap 30
#   [--work-dir DIR]           defaults to <raws-dir>/<first>---<last>/
#   [--brackets-per-stack 3]   enable bracket fusion
#   [--topmost-per-side K]     default 2
#   [--celeste-threshold T]    default 0.5
#   [--stop-after baseline]    inspect after that phase instead of continuing
```

Phases land in `<work-dir>/phase_NN_<name>/`. Each is idempotent — its
output dir existing means skip. Ctrl-C leaves a `phase_NN_<name>.tmp/`
alongside; next run refuses to proceed until you `mv` it (accept) or
`rm -rf` it (retry). Inspect or hand-edit files in that `.tmp/` between
runs as needed.

The final panorama is named `<first_stem>---<last_stem>.exr` (e.g.
`2026-04-23_100EOS5D_AAAA3089---2026-04-23_100EOS5D_AAAA3139.exr`),
so multiple panos share one parent dir without collision.

### Export

```bash
# Sanity: confirm pano.exr is display-referred (max ~1.0, not scene-linear).
scripts/pano/exr_sanity.sh pano.exr

# WebP Deep Zoom tile pyramid for pan/zoom viewers.
scripts/pano/exr_to_webp_pyramid.py pano.exr pano_dz
# -> pano_dz.dzi + pano_dz_files/

# Inspect locally with OpenSeadragon.
scripts/pano/dz_view.sh pano_dz
# -> open http://localhost:8000/viewer.html
```

## Status

- **Proven-working** on the April 2026 35-image ~360° handheld telephoto strip:
  baseline + pairwise (`--max-skip 0`) + topmost (`--per-side 2`) +
  incremental optvars + stitch_exr.
- **Not yet burned-in but scripted**: `pto_cp_celeste.sh` as a step-4a before
  pairwise. Targets sky CPs specifically; should compose cleanly with the
  others (doesn't replace them).

## Gotchas

- **EXR output is scene-linear.** The stitch phase applies the inverse sRGB
  OETF after enblend (via `exr_linearize.py`) so pixel values represent linear
  light, matching the industry EXR convention. The `hillview:encoding=linear`
  attribute records this. Tools that assume EXR = linear (darktable, Nuke,
  compositors) render correctly. To derive an 8-bit display image, apply the
  forward sRGB OETF before scaling to uchar — `exr_to_webp_pyramid.py` does
  this automatically by reading the encoding tag.
- **JPEG has a hard 65,500-pixel per-side limit.** Gigapixel panos must be
  tiled (`vips dzsave`) or downscaled for JPEG. Archival stays in EXR.
- **Hugin GUI Optimiser tab**: the mode dropdown must be "Custom parameters"
  to respect the `v` block in the PTO. Any other preset (Positions, Positions
  and view…) overrides whatever `pto_optvars.py` set. When in doubt,
  `autooptimiser -n <file>` from the CLI always honors the file's v block.
- **Intermediate warp layers** (`<prefix>NNNN.tif`) from `pto_stitch_exr.py`
  are preserved by design — re-blending is ~10 minutes, re-warping is 30+.
  Clean up manually when happy with the final EXR:
  `rm <prefix>[0-9]*.tif`.

## HDR / scene-linear (future)

Current pipeline is display-referred because darktable outputs 16-bit
sRGB-encoded TIFFs. For true scene-linear gigapixel:
- darktable output profile → linear (e.g. Rec.2020 linear), bit depth → 32f
- `raw_darktable.py --bpp 32` handles the depth change
- Everything downstream (nona, enblend) works fine on float TIFFs
- The resulting EXR would carry real HDR data, and the JPEG export would
  need actual tone-mapping (Reinhard, filmic) rather than just scale+cast
