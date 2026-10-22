# Image dimension probing review — 2026-10-21

**Status 2026-10-22:** The measurements below describe the earlier replacement
experiment. The current implementation retains JPEG-only Pillow probing for
public workers but restores auxiliary `identify -ping`, its resource settings,
and OpenCV tile decoding. Global libvips loader blocking is removed. Historical
statements about that blocking are not descriptions of the current policy.


This is a follow-up to the dependency audit, prompted by the removal of
ImageMagick's resource settings and replacement of `identify` with Pillow.
It distinguishes source-history evidence, measurements, and security inferences.
No dimension-reader replacement was made during this review. One confirmed
ImageMagick fallback-blocking defect was corrected.

## Original responsibilities and constraints

- `95cf261f` added ImageMagick resource policies in February; `01767ca3` made
  them Docker build arguments in March. These were operational settings.
- `cdb4e8d0` made libvips the main pixel reader to retain ICC profiles and
  correctly handle 16-bit sources. ImageMagick remained the dimension probe.
- `317db5ed`, `f7f0f70e`, `10327138`, `64d7ef85`, and `1e341932` successively
  corrected gamma assumptions, required EXR encoding provenance, accepted
  sidecar encoding, and rejected speculative color conversions. These rules
  apply to ordinary photos as well as panoramas.
- `5e325554` added CR2 conversion through dcraw to TIFF, including metadata
  preservation and orientation handling. CR2 is also used for individual
  camera photographs; it is not inherently a panorama format.
- `14b27aa6` added an OpenEXR header-only dimension branch and `identify -ping`
  for other inputs. The historical 8.5-minute/35-GB EXR observation concerns
  the earlier command without `-ping`; it does NOT establish that the later
  ping command decodes an EXR raster.
- The same commit documented libvips EXR full-raster processing costs, exposed
  `VIPS_DISC_THRESHOLD`, raised the dev worker container cap from 12g to 100g,
  and added external-pyramid reuse to avoid source decoding altogether.
  `e1a47b5d` subsequently required a >=2x source level for pyramid-derived
  variants to avoid near-full-resolution lossy re-encoding and seams.
- Dimensions are validated in `process_uploaded_photo` before optimized-size
  generation. CR2 conversion and metadata extraction happen earlier. The
  parent admission gate, processing timeout, subprocess crash recovery and
  shared child threads are separate from decoder-specific resource policies.

The original running image's effective ImageMagick policy was **8 GiB memory,
16 GiB map, 64 GiB disk, 500000 width/height, 12 GP area**. The Dockerfile defaults
were 2/4/8 GiB, 65536 width/height and 1 GP. Thus the actual internal deployment
had materially customized these settings. None was a universal budget for
libvips, Pillow, NumPy or dcraw.

## Measurement setup

Disposable containers only; no running service or private photo was modified.
Benign synthetic RGB images at 1024, 4096 and 8192 square, encoded as JPEG,
PNG, GIF, deflate TIFF and lossless WebP. Additional cases: EXIF orientation=6
JPEG, two-frame GIF/WebP/TIFF, halfway-truncated copies, and a valid 16384x8192
HALF RGB ZIP EXR generated in bounded scanline batches.

- Original worker image: `sha256:a78fc3de6d2a88cb1f615a87af76bad86b28f87aac10d7f149186155fd1eea3f`;
  ImageMagick 7.1.1-43 Q16. Exact historical `identify -ping -format '%w %h'`.
- Audited worker image: `sha256:72c52be8c85c82b5ae92aa73aea27045798089ded0f7b2a71f974ab25788d9e3`;
  Pillow 13.0.0, pyvips 3.1.1, system libvips 8.16.1.
- Fresh Python process per probe. Time measured after library import; includes
  lazy plugin initialization. Pillow uses the application's format list.
  Bare libvips uses `new_from_file`, no pixel operation, and its cache disabled.
  It does not import the worker policy, so bare-library fallback is observable.
- Network disabled; 2 CPUs; 1 GiB memory cap for ordinary runs, 512 MiB for
  large-EXR runs, 128 MiB for the experimental native WebP info query.
- `/proc/self/status` before/after records RSS and virtual address space;
  identify child peak RSS comes from `getrusage(RUSAGE_CHILDREN)`. That peak
  includes the fork/exec wrapper's inherited baseline (~12 MiB), so it is not
  an exact measurement of identify's own minimum footprint.
- Single runs, solid-color files, no adversarial memory-corruption payloads.
  These establish specific allocation/compatibility differences, not safety
  for all files, exact throughput, or real gigapixel performance.

Temporary reproducible scripts, fixtures, JSON logs and upstream source copies
are in `/tmp/hillview-probe-review/`: `make_fixtures.py`, `more_fixtures.py`,
`large_exr.py`, `probe.py`, `run.py`, `run_extra.py`, `run_webp_info.py`.
`probe.py MODE PATH` supports `identify`, `pillow`, `vips`, `exr`, `webp-info`.
The successful measurements are also preserved in the adjacent CSV.

## Results

All probes returned the expected raw dimensions for the static fixtures.
Orientation handling remains a separate swap performed by the worker.

For the 8192x8192 lossless WebP (67 MP, 2630 bytes compressed):

| Probe | Additional virtual address space | RSS/peak observation | Time |
|---|---:|---|---:|
| Pillow open + size | 525.5 MiB | +6.7 MiB RSS, including plugin initialization | 0.140 s |
| libvips load + width/height | 256.0 MiB | +0.2 MiB RSS | 0.006 s |
| Original identify -ping | not sampled | ~12 MiB child peak including wrapper baseline | 0.008 s |
| Native WebPGetInfo experiment | 0 MiB at measurement resolution | +0.1 MiB RSS | 0.00005 s |

Pillow's virtual growth scaled from 21.5 to 141.5 to 525.5 MiB across the
three WebP sizes; about 13.5 MiB is initialization, with the rest consistent
with two RGBA canvases. libvips grew by 4, 64 and 256 MiB: one RGBA canvas.
**Reserved address space is not equivalent to resident RAM.** The benign
probe did not touch most canvas pages. Nevertheless, these are raster-sized
allocations made merely to obtain dimensions, and can fail under constrained
address space or different allocation policies.

Source corroboration:

- Pillow 13.0.0 `WebPImagePlugin._open` reads the compressed file and creates
  `WebPAnimDecoder` (the source explicitly notes canvas allocation).
- [libvips 8.16.1 webp2vips.c](https://github.com/libvips/libvips/blob/v8.16.1/libvips/foreign/webp2vips.c)
  maps the input; `read_header` calls `vips_image_write_prepare` on an RGBA
  frame. Its nominal header path therefore allocates a canvas too.
- [ImageMagick 7.1.1-43 webp.c](https://github.com/ImageMagick/ImageMagick/blob/7.1.1-43/coders/webp.c)
  calls `WebPGetFeatures` and returns from `ReadSingleWEBPImage` in ping mode
  before `WebPDecode`. This is a distinct implementation behavior.

JPEG/PNG/TIFF Pillow probes did not exhibit raster-sized growth in these
fixtures. Bare libvips GIF probing had about 14.4 MiB extra RSS at 8192 square;
a blanket switch would have other format-specific resource effects too.

The 134-MP EXR probe was cheap in all three tested header paths:
OpenEXR header 0.00017 s, libvips dimensions 0.00721 s, identify ping 0.01008 s.
None allocated the full raster in this test. This does not contradict the
historical cost of actually materializing/converting the panorama pixels.

Compatibility differences:

- Two-frame GIF/TIFF/WebP: the old command emits `128 96128 96` with no
  separator between frames. Its old Python parsing does not yield a normal
  width/height pair. Pillow and default libvips report the first frame.
- Halfway-truncated GIF: identify exits nonzero; Pillow and libvips still
  report dimensions. Halfway-truncated JPEG and PNG give dimensions in all
  three. Truncated TIFF and WebP fail in all three.
- The native WebP info experiment also reports dimensions from a truncated
  file with an intact header. Header identification is not full-file validation.

## Security reachability findings

The scan is a package inventory, not proof of a remotely reachable RCE.

- [CVE-2026-6491](https://security-tracker.debian.org/tracker/CVE-2026-6491)
  concerns libvips' deprecated `im_minpos_vec` API; it is not the decoder path
  used here. Debian records upstream disagreement with its security status.
- [CVE-2026-88360](https://security-tracker.debian.org/tracker/CVE-2026-88360)
  concerns PFM alignment and is explicitly marked a bogus assignment by Debian.
  PFM is also outside the worker's accepted format signatures.
- Many libtiff findings name tiffcrop, tiff2pdf, thumbnail or other utilities
  the worker does not invoke. They do not justify claiming TIFF upload RCE.
- ImageMagick's [GIF advisory](https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-rvv7-5mh8-vcfc)
  and [JPEG advisory](https://security-tracker.debian.org/tracker/CVE-2026-109269)
  concern uninitialized-memory disclosure, not RCE. Upstream fixes touch GIF
  application-extension parsing and JPEG sampling-factor metadata. Both occur
  before the ping short circuit in the reviewed 7.1.1-43 source. However,
  Hillview only requests width and height, not those properties: parser
  reachability alone does not establish disclosure to the uploader.
- [CVE-2023-34152](https://security-tracker.debian.org/tracker/CVE-2023-34152)
  requires ImageMagick's optional `--enable-pipes`. The original image's
  reported configure arguments do not enable it. The application passes a
  validated absolute filename as an argv element, not shell command text.
  The package finding alone does not establish this RCE path here.
- The current distro ImageMagick still has listed issues; restoring it as a
  generic public probe is not automatically a security improvement. Nor is
  using Pillow/libvips automatically resource-equivalent or universally safe.
- EXR header parsing itself is not free of risk. For example,
  [CVE-2026-88384](https://security-tracker.debian.org/tracker/CVE-2026-88384)
  describes a header-attribute DoS affecting even 3.4.14, fixed in 3.4.16.
  The internal-only format gate remains material; the clean PyPI scan does
  not establish that the wheel's native parser is free of vulnerabilities.

## Confirmed defect fixed during this review

`operation_block_set('VipsForeignLoadMagick', True)` blocks the ImageMagick 6
loader class. The actual Debian worker image uses the separate
`VipsForeignLoadMagick7` class. An unknown class name silently has no effect.
The earlier local tests used a different native library build and missed this.

With the pre-fix policy imported in the actual audited Docker image, a
truncated TIFF reached `VipsForeignLoadMagick7File` and ImageMagick's TIFF
parser. The corrected policy blocks BOTH base classes, covering file and
buffer variants. No image decoder or dimension-reader rewrite is involved.

Validation: 26 format-policy tests pass locally. The same new file/buffer
regression script passes inside the audited Docker image, with the changed
policy mounted read-only, for flag values 0 and 1. Thus both the local and
actual system library implementations are covered. The image was not rebuilt
or deployed; the correction needs the normal deployment process.

## Decision

Do not replace all dimension probing with libvips: it reproduces the WebP
canvas-allocation problem. Keep the native pixel/color pipeline and external
pyramid bypass intact. Do not restore generic identify solely because its
resource measurements look better; its current vulnerabilities and historical
multipage behavior require separate treatment.

The narrow next candidate is libwebp's documented
[WebPGetInfo](https://developers.google.com/speed/webp/docs/api) for WebP
header dimensions. The experiment calls the installed native library via
ctypes on at most 64 KiB of input; it implements no WebP parsing or raster
processing. It worked for the tested static and animated fixtures without
canvas-sized allocation. This remains an experiment, not application code:
a production binding needs explicit decisions on supported header layouts,
malformed/truncated input, library discovery and error behavior. There is no
reason from these results to rewrite JPEG/PNG/GIF/TIFF dimension handling as
part of that narrow change.

The old subprocess timeout was also lost when probing moved into Pillow.
The overall worker processing timeout remains, but is not equivalent. Restoring
an independently timed probe is a separate operational choice, particularly
because processing threads share a child process. A generic per-job memory
cap cannot simply be imposed on that shared process without affecting siblings.
