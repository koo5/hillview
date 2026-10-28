# ExifTool GM metadata backport

Debian trixie's ExifTool 13.25 constructs a Perl PrintConv expression from GM
metadata units after deleting quotes and backslashes. That leaves interpolation
metacharacters unescaped. CVE-2026-7580 tracks this issue. JPEG-only admission is
not a sufficient reason to leave the library unchanged: ExifTool also parses
embedded metadata, and the worker uses it both to read and copy tags.

`patch_exiftool.py` applies only the conversion-escaping change from upstream
[commit 5a8b6b6ead12b39e3f32f978a4efd0233facbb01 (13.54)](https://github.com/exiftool/exiftool/commit/5a8b6b6ead12b39e3f32f978a4efd0233facbb01),
`lib/Image/ExifTool/GM.pm`. The replacement uses Perl Q/E quoting to preserve
units as literal text inside the generated expression. It does not change the
worker's JPEG, ICC, panorama or metadata-copy policy.

The Docker build runs the patch after apt updates. The patch accepts exactly
one known old fragment or exactly one already-fixed fragment. Unexpected source
fails the build for review; it does not silently skip protection. Remove this
backport when the packaged implementation includes the upstream fix, after
running the controls and compatibility trace below. Package version scanners
may continue reporting 13.25: no advisory is suppressed.

Validation uses a disposable image and the harness in
`scripts/security/run_public_jpeg_trace.sh`. The GM control constructs harmless
metadata and inspects the generated expression without evaluating its marker.
The JPEG trace covers real extraction, decoding and copying, with detector work
and artifact publication replaced by test boundaries. See
`docs/security/public-jpeg-review-2026-10-22.md` for coverage and limitations.
A successful backport test does not prove every ExifTool parser is safe or that
the original issue was exploitable through Hillview. Rebuild/recreate workers
to deploy the fix; a source bind mount cannot update the installed Perl module.
