# Public JPEG path review — 2026-10-22

Reviewed commit: `f4f1cdb9`. This is a review, not a decoder rewrite or a
claim that malformed JPEGs cannot exploit an unknown native-library bug.
No attack payloads were sent to the running service; no service was restarted.

## Path and trust boundaries

1. FastAPI parses the multipart body into Starlette's spooled upload files.
   Its upload JWT dependency runs after that body parsing.
2. `app.process` obtains the actual file size and calls the shared upload
   validator, then copies the file in 8 MiB chunks into an isolated per-job
   directory. Extension/size checks and the shared signature check apply.
3. The processing child calls `require_supported_image` before RAW conversion,
   metadata extraction or decoding. With HILLVIEW_AUX unset/false, the suffix
   must be .jpg/.jpeg and the first three bytes must be FF D8 FF. This is format
   admission, not validation of the full JPEG or its embedded metadata.
4. ExifTool reads metadata with `-json -n`. The exifread block is commented out.
   EXIF extraction happens before the dimensions/pixel-count validation.
5. Pillow opens with `formats=['JPEG']` to obtain dimensions. The caller applies
   width/height/pixel limits before generating variants. Orientation may swap
   the dimensions, as before.
6. Every normal public variant/anonymization branch reaches `blur.read_image`.
   It repeats the format gate, uses explicit libvips `jpegload`, autorotates,
   normalizes color, materializes NumPy pixels, and converts RGB to BGR.
   `_dev_only` raises unconditionally: the apparent OpenCV fallback cannot run.
7. Native libvips metadata handling and ICC conversion remain in the JPEG path.
   JPEG-only admission does not remove libexif or Little CMS from the surface.
   ExifTool also reparses source metadata when copying it to generated WebP
   output, unless fast mode skips that work.
8. External-pyramid input is disabled publicly; generated WebP output is still
   intentional. Processing children have ordinary worker filesystem, network
   and environment access. Their separation is crash recovery, not an RCE
   sandbox; shared CDN credentials are initialized in the child as well.

## Confirmed issues and limits

### Upload limit applies after multipart spooling

`app.py:42-59` describes max_part_size as the photo-upload size cap, but the
installed Starlette `MultiPartParser.on_part_data` applies it only when the
current part is NOT a file. File data goes directly to its pending write list.
The installed FastAPI handler calls request.form before solve_dependencies.
The application's actual MAX_FILE_SIZE check occurs later in `app.process`.
No explicit request-body byte cap was found in the repository Caddy configs.
An externally configured ingress limit was not assessed.

A harmless parser-only reproduction with max_part_size=1024 accepted a
2048-byte file part and rejected a 2048-byte text field. It made no HTTP request.
Reproducer: `/tmp/hillview-public-jpeg-review/multipart_limit_check.py` (temporary).
Thus oversized unauthenticated bodies can consume spool storage at the worker
boundary before JWT/size rejection unless an upstream limit intervenes. This
is a denial-of-service finding, not image-decoder RCE.

Recommended follow-up: enforce a streamed request-body budget before multipart
parsing (including bodies without Content-Length), allow bounded multipart
framing overhead, and set file/field counts deliberately. Retain the existing
actual file-size validation. Test direct worker access and ingress separately.

### Job timeout does not terminate the external-tool process tree

`worker_processing._kill_job_worker` calls only `proc.terminate()`. ExifTool
subprocesses are not placed in a separately managed job process group and have
no parent-death handling. If a processing child dies during a tool call, the
Python subprocess timeout/cleanup code dies with it. The tool can outlive the
job. This conclusion is from code inspection, not a live hung-tool experiment.

Recommended follow-up: manage and reap external tools across worker death,
with bounded termination and kill escalation. Account for concurrent jobs in
the same processing child; avoid indiscriminate process-group kills that also
kill the supervisor. Tests should use a harmless dummy tool, not an image bomb.

### Resource controls are coarse

The default 167108864-pixel limit permits about 478 MiB for ONE RGB byte raster,
before NumPy/OpenCV copies, profiles, progressive-JPEG state, model memory and
concurrent jobs. The outer process validates Pillow dimensions before decoding,
but `read_image` checks its own decoded dimensions after NumPy materialization.
A native-header limit before materialization would provide another boundary.
No mismatched-dimension bypass was demonstrated in this review.

The format gate is not a memory budget. Public limits should be justified
against actual container memory and job concurrency using representative JPEGs;
do not change them by borrowing auxiliary panorama settings.

## Installed parser inventory and advisory interpretation

Read-only queries of the local running hillview_worker on 2026-10-22 found:

| Component | Installed version |
|---|---|
| Pillow | 13.0.0 |
| libvips | 8.16.1-1+deb13u2 |
| libjpeg-turbo | 1:2.1.5-4 |
| libexif | 0.6.25-1+deb13u1 |
| Little CMS | 2.16-2+deb13u2 |
| ExifTool | 13.25+dfsg-1 |

These observations are not an assertion about every public worker or whether
its running processes have loaded the newly committed source.

The Debian trackers show the reviewed JPEG/EXIF fixes incorporated or the
relevant vulnerable code absent for the installed libjpeg/libexif versions.
The recent Little CMS integer-overflow fixes are incorporated in deb13u2.
Do not compare upstream version numbers alone when assessing Debian backports.

ExifTool still has a package-level CVE-2026-7580 finding for 13.25, involving
GM metadata PrintConv construction. Its advisory describes use of -ee; our
extraction command does not use -ee and uses -n (no print conversion). Metadata
copying does not request formatted tag output. These are relevant constraints,
not a complete proof that all embedded-metadata paths are unreachable. This
review did not demonstrate command execution or exhaustively fuzz ExifTool.
An upstream security release/backport should be evaluated independently of the
JPEG pixel loader; replacing color-managed decoding is not a fix for metadata
parsing. ExifTool's older DjVu RCE is already fixed in this installed version.

Useful primary sources:

- [libvips JPEG loader, EXIF/ICC handling and progressive-memory notes](https://www.libvips.org/API/8.17/ctor.Image.jpegload.html)
- [Debian libjpeg-turbo status](https://security-tracker.debian.org/tracker/source-package/libjpeg-turbo)
- [Debian libexif status](https://security-tracker.debian.org/tracker/source-package/libexif)
- [Debian libvips status](https://security-tracker.debian.org/tracker/source-package/vips)
- [Little CMS fixed package for CVE-2026-42798](https://security-tracker.debian.org/tracker/CVE-2026-42798)
- [ExifTool CVE-2026-7580 and upstream patch reference](https://security-tracker.debian.org/tracker/CVE-2026-7580)
- [ExifTool upstream security-release history](https://exiftool.org/history.html)

## Verification

39 format-policy tests passed again after the commit, including disguised
non-JPEG rejection, public JPEG dimensions/orientation, explicit pixel loading,
and public rejection of external-pyramid parsing. The multipart limit behavior
was reproduced against the running image's installed library, without calling
its application. No fresh image build or full native-parser fuzzing was done.

No confirmed reachable JPEG RCE was found. The upload-spooling gap and tool
lifetime gap are concrete follow-up work; metadata parsing and memory budgets
remain separate from the format-admission guarantee.

Fresh `scripts/deps.py audit --json` completed using the existing OSV binary
from `/tmp/hillview-audit-bin` on PATH. Neither Python lockfile had reported
findings. The repository-wide scan still reports Tauri dependencies and the
locally patched Appium packages, and now reports two advisories for frontend
`@vitest/mocker`. Those frontend findings are outside this JPEG-path review and
are not cleared here. Raw output is in
`/tmp/hillview-jpeg-review-repo-audit.json` (the script also prints its command).

## Instrumented follow-up — parser selection and ExifTool

The reproducible harness is in `scripts/security/run_public_jpeg_trace.sh`,
`public_jpeg_trace.py`, `HillviewTrace.pm`, and `exiftool_gm_control.pl`.
Run from the repository root:

```sh
bash scripts/security/run_public_jpeg_trace.sh \
  sha256:a208439b941dff3b9818c09e0cd86d51eaf284ae837ee562ec2b5170101866eb \
  /tmp/hillview-jpeg-trace
```

The image ID is explicit so a moving tag cannot change the tested libraries.
The runner mounts current backend source read-only, blanks the image's worker
.env file, disables networking, drops capabilities, runs as UID 1001, makes
the root filesystem read-only, and bounds RAM/CPU/PIDs and writable tmpfs.
It does not reuse the running worker's environment or volumes. These sandbox
settings apply to the investigation container, not the production service.

The corpus contains 11 small files: baseline, progressive, grayscale, CMYK,
sRGB-profiled and orientation-6 JPEGs; a malformed ICC profile; truncated and
prefix-only JPEGs; harmless trailing data; and PNG renamed to .jpg.
Production dimension, pixel and metadata helpers run with real libraries.
Production metadata copying runs after successful pixel decoding. Test-only
hooks record libvips operations, Pillow format restrictions, subprocess commands
and ExifTool directory processing/options. This is not syscall tracing of all
native internals. Hook assertions reject unexpected executable commands or
ImageMagick/TIFF/OpenEXR operations visible through pyvips.

Eight additional runs exercise create_optimized_sizes: auto, skip, manual and
precomputed anonymization modes, each with fast mode on/off. Artifact publication
is stubbed. Auto detection is stubbed to return the real read_image result and
no detections: model inference is NOT covered. Inputs are deliberately small,
so large crop variants and generated DZI pyramids are NOT exercised. This also
is not an end-to-end HTTP/authentication/admission test. Each run offers a
nonexistent external pyramid, which is declined without parsing it publicly.

Observed results, saved in `public-jpeg-trace-results-2026-10-22.json`:

- All six ordinary JPEG cases decoded; Pillow dimensions matched the decoded
  raster, including orientation. This checks dimensions and dispatch, not
  reference color accuracy (especially CMYK).
- The renamed PNG was rejected before traced metadata/pixel parsers. Prefix-only
  and halfway-truncated JPEGs failed to decode. The harmless trailing-data case
  was accepted; whole-file canonical JPEG validation is not promised.
- Pixel reads selected jpegload; profiled inputs reached icc_transform. No
  ImageMagick, RAW or alternate-format pixel decoder was observed.
- The malformed ICC sample was accepted by icc_transform. Thus malformed ICC
  input is not universally rejected by our existing error checks. Acceptance
  alone is not evidence of memory corruption or incorrect pixels.
- All eight variant runs completed. Non-fast runs copied metadata; fast runs
  did not. The only external executable observed was exiftool.
- EXIF and ICC metadata directories were reached. Extraction had PrintConv=0,
  but metadata-copy calls entered directory parsing with PrintConv=1. Therefore
  the extraction command's -n flag must NOT be treated as a blanket exclusion
  of print conversions for the entire processing path. This observation does
  not itself prove that the GM-specific conversion is evaluated during copying.

### ExifTool advisory: stronger evidence and remaining limit

The installed GM.pm constructs a conversion expression using a units string
with quotes/backslashes removed. The [upstream 13.54 fix](https://github.com/exiftool/exiftool/commit/5a8b6b6ead12b39e3f32f978a4efd0233facbb01)
instead quotes interpolation metacharacters using Perl's Q/E escaping.
The installed implementation does not contain that upstream change.

A benign positive control directly supplies one GM dictionary record with a
literal `unit$marker` units string. It records entry to Process_mrld and produces
`"$val unit$marker"` as the generated conversion expression. The control never
evaluates that expression. It demonstrates both working instrumentation and
the unescaped interpolation construction in the installed library, without
executing injected code. It is not an uploaded JPEG and does not establish
remote reachability.

No GM_DICTIONARY event appeared for the 19 corpus/mode cases. Source inspection
also shows an EmbeddedVideo JPEG-trailer route described as requiring
ExtractEmbedded, which our commands leave disabled. However, the corpus does
not include a valid GM-bearing embedded video, every vendor MakerNote, or every
ExifTool container route. Absence in this corpus is not an exhaustive
unreachability proof. The direct positive control must not be confused with a
valid embedded-container positive control.

The most defensible next change is to evaluate an upstream-fixed ExifTool
release or a narrowly scoped upstream backport, using these traces as behavior
regressions. That removes reliance on a brittle reachability argument while
preserving the pixel/color pipeline. This investigation has not applied that
change or altered production behavior. Full corpus fuzzing, public-size memory
measurements, upload-budget fixes, process-tree cleanup and credential isolation
remain separate work.

A further isolated control (`scripts/security/exiftool_patch_control.py`) copies
installed GM.pm into a temporary directory and applies only the upstream
conversion-escaping change. With the same benign dictionary input and working
trace hook, the installed parser generates `"$val unit$marker"`; the patched
copy generates `"$val unit\$marker"`. Neither expression is evaluated. This
confirms that the targeted upstream change removes interpolation of the literal
marker in this control. It does not establish whole-release compatibility or
prove an exploitable JPEG path. The runner saves both results in
`gm-patch-control.json`; production files remain untouched.

## Backport compatibility and implementation

The next step is now implemented as a small build-time backport in
`backend/worker/security/patch_exiftool.py`, documented in the adjacent README
and invoked by the worker Dockerfile immediately after apt package installation.
It applies only the upstream GM conversion-escaping change. It recognizes the
already-fixed fragment and rejects unknown/duplicate/mixed fragments without
writing. No decoder, color-management, metadata selection or auxiliary policy
was changed.

An isolated image, `hillview-worker:exiftool-review`, was built from the exact
previously tested image plus this helper. The build applied the fix and then
successfully ran it again to check idempotence. The image ID and comparison
results are recorded in `public-jpeg-trace-results-2026-10-22.json`.

All 19 complete JSON trace objects from the patched image exactly matched the
original image's results. The marker-control expression is now escaped in the
patched image. Additional explicitly allowlisted ordinary-unit controls evaluate
the generated conversions for `rpm`, `kph` and `widgets/s`; outputs before and
after are respectively `12.50 rpm`, `12.50 km/h`, and `12.5 widgets/s`. The marker
expression is still never evaluated. These ordinary formatting checks were
also rerun successfully against the already-patched image.

One harness-only issue was corrected during this work: directly calling
GetValue on the standalone dictionary control did not populate a value. The
ordinary-unit test now evaluates only the three allowlisted benign expressions.
It does not accept arbitrary test expressions. The source-drift guard was also
checked with unknown, duplicate-old and mixed-old/new contents; each was
rejected without mutation.

This is a candidate backport with finite compatibility evidence, not a claim
of complete ExifTool safety or proof of a remotely exploitable original bug.
The complete production Dockerfile was not rebuilt from fresh apt repositories;
the isolated build validates the exact patch/install step on the reviewed
package set. No running worker was replaced. A normal worker rebuild and
recreation are still required to deploy it. The scripts, evidence and backport
remain uncommitted for review.
