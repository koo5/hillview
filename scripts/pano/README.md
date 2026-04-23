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
| `exr_sanity.sh` | Report an EXR's pixel range and classify display-referred vs scene-linear |
| `exr_to_webp_pyramid.py` | Convert a display-referred EXR to a WebP Deep Zoom tile pyramid |
| `dz_view.sh` | Serve a DZI pyramid locally with OpenSeadragon for quick inspection |
| `xmp_module.py` | Edit a named darktable module across all XMP sidecars (raw-stage utility) |

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
# Create Hugin project with CPs. GUI: add TIFFs and run Assistant once.
# Or CLI:
pto_gen *.tif -o pano.pto
cpfind --linearmatch -o pano.pto pano.pto

# Reset positions to a clean horizontal baseline. Discards whatever the
# Assistant's optimizer drifted to — parallax-poisoned CPs make it lie.
scripts/pano/pto_horizontal_baseline.py pano.pto --overlap 30 -o s1.pto

# Clean CPs. Three filters, each targets a different failure mode:
#   - celeste:  sky/cloud false matches between distant frames
#   - pairwise: any remaining non-adjacent false matches
#   - topmost:  drops bottom-of-frame CPs where parallax is worst
scripts/pano/pto_cp_celeste.sh        s1.pto s2.pto
scripts/pano/pto_cp_pairwise.py       s2.pto --max-skip 0 -o s3.pto
scripts/pano/pto_cp_topmost.py        s3.pto --per-side 2 -o s4.pto

# Optimize incrementally — unlock yaw first, confirm, then pitch, then roll.
scripts/pano/pto_optvars.py s4.pto --free y -o opt.pto
autooptimiser -n opt.pto -o opt.pto
scripts/pano/pto_optvars.py opt.pto --free y,p -o opt.pto
autooptimiser -n opt.pto -o opt.pto
scripts/pano/pto_optvars.py opt.pto --free y,p,r -o opt.pto
autooptimiser -n opt.pto -o opt.pto

# Stitch to EXR. Warped intermediates are kept on disk so a failed blend
# doesn't cost the 30+ minute nona step.
scripts/pano/pto_stitch_exr.py opt.pto --prefix pano
# -> pano.exr (plus pano0000.tif .. panoNNNN.tif until you `rm` them)
```

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

- **EXR output is display-referred**, not scene-linear — darktable's default
  output profile is sRGB, so the values in `pano.exr` are sRGB-encoded floats
  in `[0, 1]`. To derive an 8-bit image: multiply by 255, cast to uchar,
  **no additional gamma curve**. Applying `colourspace srgb` double-encodes.
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
