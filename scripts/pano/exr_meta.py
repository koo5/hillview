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
When absent:          rejected by the Hillview worker.

Why no default: silent guesses silently miscolor uploads. A scene-linear
gigapixel pano with max ≈ 0.9 (overcast scene) is byte-indistinguishable
from a display-referred pano of the same content; only the producer
knows which one it actually is. Tag at the source; the cost is one CLI
invocation per export.

Linearity is orthogonal to dynamic range. A scene-linear EXR bounded in
[0, 1] is still scene-linear; a display-referred EXR can technically
contain values > 1.0 (unusual).

=== Worker contract ===

A conformant reader decides the transfer function as:
	encoding = exr.header().get("hillview:encoding")
	if encoding is None:
			raise ValueError("EXR is missing required hillview:encoding")
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

=== Performance note ===

OpenEXR stores the header before pixel data, so updating the header
means rewriting the whole file. `set_encoding` uses the modern
OpenEXR.File API, which loads all channels into numpy arrays
(separate_channels=True), mutates the header dict in place, and writes
a new file. RAM = total uncompressed pixel data (e.g. ~9 GB for a
gigapixel 4-channel float32; ~4.5 GB for half). Wall time is dominated
by PIZ decompress+recompress (~1–2 min for a gigapixel half-float).

Why the modern API: the legacy InputFile/OutputFile path silently drops
custom-named string attributes — `header['hillview:encoding'] = 'linear'`
on a legacy OutputFile produces a file that does NOT contain the
attribute, with a printed `XXX - unknown attribute` warning on read.
The File API correctly serializes the attribute as a standard EXR
string-typed attribute that legacy and modern readers both parse.

If wall time or RAM becomes the pain point, Tier B remains an open option:

	Tier B  — byte-level header surgery (fast, low RAM).
						Skip the OpenEXR library entirely. Parse the header bytes
						directly, splice in the new attribute, shift the offset
						table + pixel data forward by that many bytes, and rewrite
						the offset table entries with `+shift`. Pixel data is
						copied verbatim via os.sendfile so it's pure disk I/O —
						expect 5–10 seconds on a 3 GB EXR (bound by sustained
						write throughput). Code: ~60 lines. Risk: bugs corrupt
						files until we add a `show` round-trip test. Write the
						test first, then the surgery.

						EXR header layout reference (for when the time comes):
							- magic (4B) + version (4B)
							- attributes: [name\0][type\0][size:u32_le][value:size]*
							- header terminator: single null byte
							- offset table: u64_le[chunk_count]  (scanline-based:
								ceil(height / scanlines_per_chunk); tile-based differs)
							- pixel data chunks (copy verbatim, no re-encoding)
						Inserting a StringAttribute "hillview:encoding" = "srgb"
						= len("hillview:encoding")+1 + len("string")+1 + 4 + 4
						= 33 bytes to shift. Update every offset_table[i] += 33.

=== Security-minded alternative: pure-Python header reader ===

The worker calls `_exr_encoding` on every uploaded EXR, which means the
`OpenEXR` Python binding's C++ parser runs on attacker-controlled bytes
in addition to pyvips's already-existing EXR parse path. Two libopenexr
instances in the ingest chain doubles the CVE surface.

If that surface matters (it does for a public photo-upload service), a
pure-Python attribute reader can replace `_exr_encoding` entirely for
the attribute-read use case — the worker keeps `OpenEXR` only if it
also needs to *write* (which it currently doesn't; only the stitch
pipeline writes).

Sketch (untested — roughly 30 lines when fleshed out):

		import struct

		_EXR_MAGIC = b'\\x76\\x2f\\x31\\x01'

		def read_hillview_encoding(path, max_header_bytes=65536):
				\"\"\"Return the hillview:encoding value from an EXR, or None if
				the attribute is absent. Reads at most max_header_bytes to avoid
				unbounded header walks on malformed input.\"\"\"
				with open(path, 'rb') as f:
						head = f.read(max_header_bytes)
				if not head.startswith(_EXR_MAGIC):
						raise ValueError(f"not an EXR file: {path}")
				# Skip 4B magic + 4B version flags.
				pos = 8
				while pos < len(head):
						# Attribute name: null-terminated string.
						end = head.index(b'\\0', pos)
						name = head[pos:end].decode('ascii', errors='replace')
						pos = end + 1
						if not name:
								return None  # header terminator
						# Attribute type: null-terminated string.
						end = head.index(b'\\0', pos)
						# (type = head[pos:end].decode('ascii'))
						pos = end + 1
						# Size: 4B little-endian uint32.
						if pos + 4 > len(head):
								raise ValueError(f"truncated header in {path}")
						size = struct.unpack('<I', head[pos:pos+4])[0]
						pos += 4
						if pos + size > len(head):
								raise ValueError(f"truncated header in {path}")
						value = head[pos:pos+size]
						pos += size
						if name == 'hillview:encoding':
								return value.decode('ascii', errors='replace')
				raise ValueError(f"no header terminator within {max_header_bytes}B")

Attack surface of the above: `struct.unpack`, `bytes.index`, and
`.decode` — all stdlib. No image data is ever touched. No
decompression. A malicious EXR's worst case is a ValueError at ingest.

Keep `OpenEXR` as a dep for the stitch pipeline's `exr_meta.py set`
path. Only the read side in the worker switches.

=== What about pre-allocating padding in the header? ===

Considered and rejected for the current shape of the problem. The idea:
have enblend (or a post-enblend pass) reserve N bytes of header padding
(e.g. a dummy "_reserved" string attribute) so later attribute writes
can overwrite the padding in place, no shift.

Why it doesn't pay off here:

	- enblend has no flag for custom EXR attributes. Reserving padding
		would require either patching enblend's source or adding a
		post-enblend byte-level pass — and that post-enblend pass IS the
		expensive operation we're trying to skip. The first rewrite is the
		one that costs time; subsequent in-place overwrites are cheap.
		We only call set_encoding once per stitch, so there are no
		"subsequent" writes to amortize the first one over.

	- Tier B (byte-level header surgery) is fast enough on its own
		without any precondition on the file having padding. It pays one
		shift of ~33 bytes per set, and pixel data is copied via sendfile
		at raw disk throughput.

When padding WOULD be worth it: if Hillview later adds more diagnostic
attributes (pixel stats, provenance, ingest history) and each
`exr_meta set`/`add` call should be sub-second. At that point: reserve
a ~1 KB `hillview:_reserved` padding attribute on the first write (via
Tier B), then grow new real attributes into the padding in place.

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
		f = OpenEXR.File(path, header_only=True)
		header = f.header()
		if ENCODING_ATTR not in header:
				return None
		raw = header[ENCODING_ATTR]
		return raw.decode() if isinstance(raw, bytes) else str(raw)


def set_encoding(path: str, encoding: str) -> None:
		"""Rewrite the EXR at `path` with hillview:encoding=<encoding>.

		Loads via OpenEXR.File (modern API, separate_channels=True), mutates
		the header dict in place, and writes a new file via atomic temp +
		rename. Pixel data round-trips bit-exact; channel storage types
		(HALF/FLOAT) are preserved. A partial temp file is left for
		inspection if the write raises mid-flight."""
		if encoding not in VALID_ENCODINGS:
				raise ValueError(
						f"encoding must be one of {VALID_ENCODINGS}; got {encoding!r}"
				)

		f = OpenEXR.File(path, separate_channels=True)
		f.header()[ENCODING_ATTR] = encoding

		tmp_path = path + ".tmp"
		f.write(tmp_path)
		os.replace(tmp_path, path)


def cmd_set(args: argparse.Namespace) -> int:
		set_encoding(args.file, args.encoding)
		print(f"{args.file}: {ENCODING_ATTR} = {args.encoding}")
		return 0


def cmd_show(args: argparse.Namespace) -> int:
		f = OpenEXR.File(args.file, header_only=True)
		header = f.header()
		hillview_attrs = {
				k: (v.decode() if isinstance(v, bytes) else str(v))
				for k, v in header.items()
				if k.startswith("hillview:")
		}

		if not hillview_attrs:
				print(f"{args.file}: no hillview:* attributes")
				print(f"  (the Hillview worker rejects EXRs missing {ENCODING_ATTR};")
				print(f"   tag with: exr_meta.py set FILE --encoding {{srgb,linear}})")
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
