# Panorama upload: archived source and served images differ

Investigation: 2026-10-27. This note is intended to be saved alongside the
`autocopy_done/2026-08-31` archive. All paths below are relative to
`2026-08-31/DCIM/100EOS5D/cr2/` unless stated otherwise.

## Identification and preservation decision

Photo: https://hillview.cz/photo/hillview-42b675fc-a4ef-4ed7-a69f-d62a2d778bfc

Source basename:
`2026-08-31_100EOS5D_AAAE2378---2026-08-31_100EOS5D_AAAE2410.exr`.

**Keep the uploaded images and pyramid. Do not reupload or rerender this photo.**
The operator chose to make Hillview's photo dimensions describe the uploaded
artifacts: **157,180 × 10,646**, replacing **156,962 × 8,366** in the photo row.
The operator applied the metadata repair to production on 2026-10-28 and
refreshed the local dump. Read-only verification confirms the new row dimensions
and matching served-pyramid metadata; source MD5 and empty detection JSON remain
unchanged. The production backup table is
`public.photo_size_fix_f28e4b89a344ddce`. No archive files or uploaded image bytes
were changed.

The archived EXR must remain as it is. It is a different render from the one
represented by Hillview's served images. The recorded source MD5 continues to
identify the archived upload input; changing dimensions does not establish that
the served pixels were derived from those exact bytes.

## Verified evidence

| Item | Dimensions / identity |
|---|---|
| Archived `pano1/phase_12_exr_render/<basename>.exr` | 156,962 × 8,366 in both EXR `dataWindow` and `displayWindow` |
| Archived EXR size | 4,441,857,821 bytes |
| Archived EXR MD5 | `5a880e0b0c8f0eef7eb92b5e25d1509f`, exactly matching the photo row's `file_md5` |
| Archived `pano1/phase_13_pyramid/<basename>.dzi` | 156,962 × 8,366 |
| Photo row before repair | 156,962 × 8,366 |
| Served DZI descriptor and saved pyramid metadata | 157,180 × 10,646 |
| Served full image header and its metadata | 8,192 × 554, a capped rendition with the served pyramid's aspect |
| Six numeric renditions | Their headers/metadata agree with the served full/pyramid aspect |
| Stored detections | `{"objects": [], "manual": true}`; no boxes to transform |
| Recorded worker | `ktiff_20260902-075814_e2bd3` |

The served DZI is under
`https://pics.hillview.cz/pics2/opt/dzi/8e807659-a66b-4413-aa54-c04273263513/42b675fc-a4ef-4ed7-a69f-d62a2d778bfc.dzi`.
The served full is under the same host and pool, at
`opt/full/8e807659-a66b-4413-aa54-c04273263513/42b675fc-a4ef-4ed7-a69f-d62a2d778bfc.webp`.

## Timeline recovered from the archive

Times are **UTC on 2026-09-02**. The original `ls` display on ktiff used CEST,
two hours ahead of UTC. Manifest times are file mtimes, not request start times.

| Time | Event |
|---|---|
| 08:35:31 | A `prod` upload manifest records failure: worker could not register its processing result with the API. |
| 08:47:58 | A later `prod` manifest records `created`, photo `a9686561-9cf4-47b7-9c5e-750bf92b53af`. This earlier ID was not found in the restored production dump. |
| 11:56:13 | `prod2` records `duplicate`. |
| 12:03:03 | `prod3` records `duplicate`. |
| 12:25:56 | `prod4` records `duplicate`. |
| 16:16:56 | Current archived EXR's mtime, after the canvas change and rerender. |
| 16:22:10 | Current archived DZI's mtime. |
| 17:19:03.670030 | Current photo row's upload time. |
| 17:29:13.422469 | Current photo row's completion time. |
| 17:29:13.671388 | `prod5` manifest records `created`, current photo ID `42b675fc-a4ef-4ed7-a69f-d62a2d778bfc`. |
| 17:29:13.871383 | `prod5/pano1/` upload-marker symlink's mtime. |

`pano1/_pano_run.log` records an earlier render at **157,180 × 10,646**, then
`--nuke-after canvas`, a canvas rebase, and rerenders at **156,962 × 8,366**.
The latter size matches both surviving EXR windows and the archived DZI.

The five `uploaded/prod*/pano1/<basename>.exr` markers are symlinks to the
**same pathname**, not snapshots of five EXRs. Their absolute links still point
into `/home/koom/autocopy/`, so they are dangling after archival under
`/home/koom/autocopy_done/`. Read the corresponding file inside the archive.
The `.manifest.*.json` files in each `uploaded/prod*/` directory distinguish
created uploads, duplicate responses, and the failed attempt. Five markers
do not mean five successful processing runs.

## Reproduced failure mechanism and remaining uncertainty

The strongest explanation is a stale **libvips image-load operation cache**
when an EXR pathname is reused after rerendering. This was reproduced locally
using the actual Hillview worker's `blur.read_image()`, libvips 8.16.1, and its
default cache limit of 100 operations:

1. Write and decode a 30 × 20 EXR.
2. Atomically replace that pathname with a 28 × 15 EXR with a different mtime.
3. The worker's fresh OpenEXR header probe returns 28 × 15.
4. The pyvips-based decoder returns the cached 30 × 20 raster.
5. Disabling the operation cache in that isolated test process makes decoding
   return 28 × 15 as well.

The worker separately preserves preliminary header dimensions for the photo
row, while generating renditions and pyramids using decoded-raster dimensions.
It can therefore report new-source dimensions alongside outputs made from an
older cached raster. This does not require simultaneous uploads or cached
pyramid files: a newly generated pyramid can contain the old raster's pixels.

This is a reproduced software defect and fits the archived history and observed
geometry. It is **not proof of the historical decoder cache contents**. The
September processing logs were not recovered. A separate synthetic test of
different EXR data/display windows did not reproduce the discrepancy; the actual
archived EXR has identical data/display windows anyway.

Git tree `38052518` (2026-08-21) already contains the separate probe/decoded-size
paths, before this upload. The exact deployed commit was not established.
Ordinary upload authorization stores no dimensions, and completion writes
photo dimensions and rendition metadata together. The newer archived source
has its own MD5 and the final manifest records a new photo ID, so the evidence
does not require dimensions retained from an earlier authorization.

## Metadata repair scope

Change only `photos.width` and `photos.height` for the current photo to
**157180** and **10646**. Keep the existing rendition/pyramid metadata, URLs,
source MD5, EXIF/provenance, and detection JSON. The full's 8192 × 554 dimensions
are a downscale and must not replace the original uploaded-raster dimensions.

The repair tool must check current values, source identity, and served DZI
dimensions, and save a durable before/after backup. This note deliberately
retains the archived source dimensions so a future reader can distinguish
source identity from the coordinate space of the preserved uploaded artifacts.

## Worker cache correction, 2026-10-28

libvips documents this behavior: file-load operations may return the cached
image after a file is replaced, and the loader's `revalidate` option forces a
fresh load. See the version-matched documentation:
https://www.libvips.org/API/8.16/How-it-opens-files.html#caching

The worker's installed libvips 8.16.1 exposes `revalidate` on both the EXR and
JPEG loaders. The worker source now passes `revalidate=True` on each auxiliary
`pyvips.Image.new_from_file()` and public `pyvips.Image.jpegload()` call in
`backend/worker/blur.py`. This refreshes each input load while keeping the
process-wide operation cache enabled for concurrent jobs. It does not require
clearing the cache globally, hashing the EXR, or relying on mtime changes.

Five real-decoder regression tests all failed before the correction and pass
after it, using synthetic images in isolated processes with the normal cache:

- EXR replaced by an image with different dimensions and mtime.
- EXR replaced with different pixels but the same dimensions and mtime.
- EXR symlink retargeted to a different image.
- Public JPEG replaced with different pixels at the same dimensions and mtime.
- Auxiliary JPEG replaced in the same way.

Each test verifies pixel colors as well as dimensions, that an already-returned
raster stays valid, and that the global cache limit remains enabled/unchanged.
The tests are in `backend/worker/tests/unit/test_image_load_cache.py` and run
with either pytest or standard-library unittest. This patch is prepared locally;
it needs worker deployment. The preserved panorama is not reuploaded.

## Worker dimension correction, 2026-10-28

The second worker correction carries the final raster/pyramid coordinate space
out of rendition generation in an `OptimizedPhoto` result. The processing
response now takes its dimensions from that result rather than the preliminary
probe. A capped `full` rendition does not reduce the photo-row dimensions, and
the accepted external-pyramid path still avoids decoding the source.

If a pyramid was accepted before decoding but the worker subsequently decodes
the source, its dimensions are checked against the actual raster before any
variants are published. A disagreement fails the job instead of publishing
inconsistent outputs. Detection coordinates and decisions are preserved.

Four regressions reproduced the old dimension-return/early-pyramid problems;
all seven end-to-end dimension cases now pass, including rotation and capped
renditions. The supported `backend/worker/run_unit_tests.sh` runner passed all
98 targeted worker tests covering image formats, pyramids, processor helpers,
cache freshness and the new dimension cases. No database or existing photo was
changed. This source correction also needs worker deployment.
