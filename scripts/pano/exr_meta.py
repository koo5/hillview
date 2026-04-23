#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "OpenEXR",
# ]
# ///
"""
OpenEXR metadata helper for Hillview panoramas.

=== Hillview EXR convention ===

Attribute:            hillview:encoding
Valid values:         "srgb"    pixels are display-referred; the sRGB
                                transfer function has been applied to each
                                channel before writing.
                      "linear"  pixels are scene-linear.
Default when absent:  "srgb".

Why this default: the typical hobbyist panorama pipeline (RAW developer
→ sRGB TIFF → Hugin/nona → enblend → EXR) produces display-referred
content even though the EXR container's industry convention is linear.
Hillview treats unmarked EXRs as display-referred so the common case
"just works"; scene-linear producers (CG renders, truly HDR pipelines)
must tag their files explicitly.

Linearity is orthogonal to dynamic range. A scene-linear EXR bounded in
[0, 1] is still scene-linear; a display-referred EXR can technically
contain values > 1.0 (unusual).

=== Worker contract ===

A conformant reader decides the transfer function as:
  encoding = exr.header().get("hillview:encoding", "srgb")

  if encoding == "srgb":
      # pixels already carry the sRGB OETF — DO NOT re-apply on display
      display = pixels
  elif encoding == "linear":
      # apply sRGB OETF for display
      display = apply_srgb_oetf(pixels)
  else:
      raise ValueError(f"unknown hillview:encoding value: {encoding!r}")

=== Commands ===

  set   FILE --encoding srgb|linear    Write the attribute in-place.
  show  FILE                           Dump hillview:* attrs on FILE.

(More commands — stats, check — likely added later for diagnosis.)

=== Memory note ===

OpenEXR stores the header before pixel data, so updating the header means
rewriting the whole file. This implementation reads all channel data into
memory, updates the header, and writes a new file + atomic rename. A 1
gigapixel half-float RGB EXR needs roughly 6 GB of RAM during the rewrite.
A streaming (scanline-chunked) implementation would cut that; not yet
worth the added code until a file actually breaks.

Invocation:
    ./exr_meta.py show pano.exr
    # or, explicitly:
    uv run exr_meta.py show pano.exr
    # or, if you prefer pip and have OpenEXR already installed:
    python3 exr_meta.py show pano.exr

The shebang uses `uv run --script` so PEP 723 inline dependencies below
are resolved automatically into an ephemeral venv on first run.
"""

import argparse
import os
import sys

try:
    import OpenEXR
except ImportError as e:
    sys.exit(
        f"error: OpenEXR Python binding not installed ({e}).\n"
        f"install with: pip install OpenEXR"
    )


ENCODING_ATTR = "hillview:encoding"
VALID_ENCODINGS = ("srgb", "linear")
DEFAULT_ENCODING = "srgb"


def read_encoding(path: str) -> str | None:
    """Return the hillview:encoding value stored in the EXR, or None if the
    attribute is not set. Callers that need a value should fall back to
    DEFAULT_ENCODING themselves, so this function never hides absence."""
    exr = OpenEXR.InputFile(path)
    try:
        header = exr.header()
        if ENCODING_ATTR not in header:
            return None
        raw = header[ENCODING_ATTR]
        return raw.decode() if isinstance(raw, bytes) else str(raw)
    finally:
        exr.close()


def set_encoding(path: str, encoding: str) -> None:
    """Rewrite the EXR at `path` with hillview:encoding=<encoding>.

    Reads all pixel data into memory, writes a temp file with the updated
    header, then atomically renames over the original. Errors propagate —
    no bare except, no silent failures. A partially-written temp file is
    left in place for the user to inspect if the write raises mid-flight."""
    if encoding not in VALID_ENCODINGS:
        raise ValueError(
            f"encoding must be one of {VALID_ENCODINGS}; got {encoding!r}"
        )

    exr = OpenEXR.InputFile(path)
    try:
        header = exr.header()
        channels = header["channels"]
        # Read every channel fully. Memory-heavy for large files; see docstring.
        pixel_data = {
            name: exr.channel(name, ch.type) for name, ch in channels.items()
        }
        header[ENCODING_ATTR] = encoding
    finally:
        exr.close()

    tmp_path = path + ".tmp"
    out = OpenEXR.OutputFile(tmp_path, header)
    try:
        out.writePixels(pixel_data)
    finally:
        out.close()
    os.replace(tmp_path, path)


def cmd_set(args: argparse.Namespace) -> int:
    set_encoding(args.file, args.encoding)
    print(f"{args.file}: {ENCODING_ATTR} = {args.encoding}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    exr = OpenEXR.InputFile(args.file)
    try:
        header = exr.header()
        hillview_attrs = {
            k: (v.decode() if isinstance(v, bytes) else str(v))
            for k, v in header.items()
            if k.startswith("hillview:")
        }
    finally:
        exr.close()

    if not hillview_attrs:
        print(f"{args.file}: no hillview:* attributes")
        print(f"  (a reader will default to {ENCODING_ATTR}={DEFAULT_ENCODING!r})")
        return 0

    for k, v in hillview_attrs.items():
        print(f"{k} = {v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="write hillview:encoding attribute")
    p_set.add_argument("file")
    p_set.add_argument(
        "--encoding", required=True, choices=VALID_ENCODINGS,
        help="'srgb' = display-referred, 'linear' = scene-linear",
    )
    p_set.set_defaults(fn=cmd_set)

    p_show = sub.add_parser("show", help="print hillview:* attributes")
    p_show.add_argument("file")
    p_show.set_defaults(fn=cmd_show)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
