# ExifTool follow-up — 2026-10-25

Stronger isolation is explicitly deferred to
[the separate TODO thread](../todo/worker-parser-isolation.md). This review
continues the public JPEG/ExifTool investigation without changing production
parsing behavior or replacing a running service.

## Upstream changes assessed

Checked upstream master at `2200871d9cef988051d2a99d67df3bda6cbb30a8`
(13.59). Its history identifies 13.55 as the production release and 13.59 as a
later development release. This distinction matters when evaluating a full
upgrade. Reviewed source diffs, not just package/advisory version labels.

| Release | Security-related source change | Hillview relevance |
|---|---|---|
| 13.50 | macOS metadata-writing commands changed from shell strings to argument lists | The reviewed worker is Linux; these macOS commands are outside its path. |
| 13.53 | Windows window-title command restricts allowed characters | Windows-only code; no public worker title/progress option is used. |
| 13.54 | GM dictionary units escaped when constructing PrintConv expressions | Addressed by the tested narrow backport. Do not rely on JPEG admission or extraction's `-n` to exclude the metadata-copy path. |
| 13.59 | CLI output formatting strips directories from metadata-derived `%o` output filenames | Source review finds this relevant to `-W` output filename formatting. Hillview uses neither `-W` nor metadata-derived output filename templates; output paths are supplied by the application. This reachability assessment is an inference from the reviewed commands and source, not a general statement about all ExifTool use. |

The 13.59 source also changes XMP error reporting and adds explicit piped config
support. The worker does not request `-config -` or JSON/CSV metadata import.
Normal implicit ExifTool configuration remains operator-controlled; this review
does not assume it is a safe sandbox if an attacker can already write executable
configuration into its lookup locations.

Other changes deserve separate correctness/resource consideration: the history
mentions Google HDRP handling and XMP parsing fixes. A security-labelled changelog
entry is not the complete universe of changes that could matter to robustness.
No additional applicable RCE fix was established in the reviewed labelled
releases; this is not proof that unlabelled defects or unknown bugs cannot exist.

Sources:

- [Pinned upstream history](https://github.com/exiftool/exiftool/blob/2200871d9cef988051d2a99d67df3bda6cbb30a8/Changes)
- [13.50 macOS changes](https://github.com/exiftool/exiftool/commit/e9609a9)
- [13.53 Windows changes](https://github.com/exiftool/exiftool/commit/7025cfa)
- [13.54 GM fix](https://github.com/exiftool/exiftool/commit/5a8b6b6ead12b39e3f32f978a4efd0233facbb01)
- [13.59 changes](https://github.com/exiftool/exiftool/commit/2200871d9cef988051d2a99d67df3bda6cbb30a8)
- [Debian package security tracker](https://security-tracker.debian.org/tracker/source-package/libimage-exiftool-perl)

## Expanded metadata corpus and full-release candidate

A disposable candidate image overlays upstream 13.59 Perl libraries and CLI on
the previously reviewed worker image. It is tagged
`hillview-worker:exiftool-13.59-review`, immutable ID
`sha256:5a563038c4e0cbb8d4f718500bf08e4c794dec732d60388986ef146050c58e15`.
This is an investigation image, not a production installation recipe: dpkg's
ExifTool package metadata still describes the underlying Debian package.

The existing 19-case JPEG/variant harness passes on this image, with complete
trace JSON exactly equal to the narrow-backport image's trace. Detector work
and artifact publication remain stubbed as documented in the earlier review.

The new `scripts/security/exiftool_metadata_corpus.py` selects the 42 JPEG-magic
fixtures in upstream `t/images` at the pinned commit. It runs the exact metadata
extraction and copying argument lists, then reads tags back from generated WebP
artifacts. These upstream metadata fixtures are not necessarily decodable photos;
this is parser-surface and metadata compatibility testing, not proof they would
pass every upload/pixel check. Fixtures are copied into private temporary storage.
The `.jps` fixture is renamed `.jpg` for the test.

Two controls bring the total to 44 cases: a small JPEG with the upstream
QuickTime.mov appended, and that MOV tested directly. The MOV is a test-only
positive control, never a proposed public input. Both controls are also read
with `-ee` to compare dispatch; ordinary worker commands do not use it.

Observed parser surface:

- 108 distinct ExifTool directory tables are reached from the JPEG cases on the
  narrow backport, and 109 on 13.59, excluding the direct MOV control.
- MakerNotes, ICC, XMP, Photoshop, FLIR and other vendor data are genuinely
  parsed even without `-ee`. JPEG-only admission is not JPEG-only metadata.
- No GM_DICTIONARY event occurred. The earlier direct GM control remains the
  instrumentation's positive check; we still lack a valid GM-bearing JPEG or
  embedded-video positive control for whole-file reachability.
- The direct MOV invokes QuickTime parsing. Simply appending it to the JPEG
  did not invoke those directories, even with `-ee`. Therefore the appended
  fixture must NOT be treated as a successful embedded-video positive control
  or as proof that every embedded-video route is disabled.
- All 43 JPEG-source metadata copy commands succeeded on both versions.

Extracted metadata changes across releases occur in Canon.jpg, Canon1DmkIII.jpg
and Google.jpg (Canon flash fields and expanded/renamed Google HDRP fields).
Consequently a full upgrade is a wider metadata compatibility change than the
GM backport even though the small original corpus had identical traces.
The compact comparison artifact includes per-fixture hashes, exit statuses,
changed tag names, and the reached directory tables.

## Reproduction

Clone the official upstream repository into temporary storage and check out the
pinned commit above. With its `t/images` mounted at `/fixtures`, run:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 32 \
  --user 1001:1001 --tmpfs /tmp:rw,size=64m \
  -v "$PWD/scripts/security:/review/probes:ro" \
  -v /tmp/hillview-exiftool-upstream/repo/t/images:/fixtures:ro \
  -e PERL5LIB=/review/probes -e PERL5OPT=-MHillviewTrace \
  --entrypoint python IMAGE_ID /review/probes/exiftool_metadata_corpus.py
```

Use immutable image IDs for a recorded run. No live request, private photo,
network credential, or production volume is required. These are benign fixtures,
not exhaustive fuzzing or a demonstrated exploit. The fixture signatures and
hashes in the results make the selected corpus reviewable without vendoring
upstream images.

## Current decision

Retain the reviewed GM backport as the narrow fix for the known applicable
expression-construction issue. Do not silently replace it with the development
release solely because its version number is newer. The full-release candidate
is now concrete and tested enough to discuss its metadata behavior changes;
a deliberate upgrade can be evaluated separately.

Known-flaw remediation and parser-sandbox strength remain different questions.
No newly demonstrated JPEG RCE was found in this review. Residual uncertainty
includes untested embedded formats, malformed metadata combinations and unknown
parser defects. The separate isolation TODO records how to contain those risks.

### Copy readback results

All 43 generated WebP artifacts were successfully read back on both versions.
The comparison ignores tool version, filesystem timestamps/path and file size.
Differences occur in the Canon flash and Google HDRP fields above, XMPToolkit
fields in several XMP-bearing outputs, and PreviewImageStart in two Olympus
outputs. The evidence JSON records the exact changed tag names by fixture.
Readback uses each candidate's own reader, so these differences can reflect
changed interpretation as well as changed bytes written; they must not be
presented as demonstrated corruption or loss. A future full-upgrade decision
should compare both outputs with one common reader and representative real
photos before deciding whether any difference requires migration handling.
