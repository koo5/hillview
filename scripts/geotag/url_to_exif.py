#!/usr/bin/env python3
"""Extract lat, lon, bearing from a Hillview URL and output either exiftool
arguments or a JSON metadata blob.

Usage:
	./url_to_exif.py 'https://hillview.cz/?lat=50.17&lon=14.46&bearing=77.87'
	exiftool $(./url_to_exif.py 'URL') photo.tif

	# JSON mode (for formats exiftool can't write, e.g. EXR) — matches the
	# worker's BrowserMetadata schema so it can be fed to upload-files
	# --metadata directly:
	./url_to_exif.py --json 'URL'
	upload-files --metadata (./url_to_exif.py --json 'URL') pano.exr
"""

import json
import sys
from urllib.parse import urlparse, parse_qs

args_in = sys.argv[1:]
json_mode = False
if args_in and args_in[0] == '--json':
	json_mode = True
	args_in = args_in[1:]

if not args_in:
	print(f"Usage: {sys.argv[0]} [--json] '<hillview-url>'", file=sys.stderr)
	sys.exit(1)

params = parse_qs(urlparse(args_in[0]).query)

lat = params.get("lat", [None])[0]
lon = params.get("lon", [None])[0]
bearing = params.get("bearing", [None])[0]

if not lat or not lon:
	print("Error: could not extract lat/lon from URL", file=sys.stderr)
	sys.exit(1)

lat_f = float(lat)
lon_f = float(lon)

if json_mode:
	out = {"latitude": lat_f, "longitude": lon_f}
	if bearing:
		out["bearing"] = float(bearing)
	# Compact separators so shell word-splitting (e.g. fish's `(...)`)
	# treats the whole blob as a single argument.
	print(json.dumps(out, separators=(',', ':')))
	sys.exit(0)

args = [
	f"-GPSLatitude={lat}",
	f"-GPSLongitude={lon}",
	f"-GPSLatitudeRef={'S' if lat_f < 0 else 'N'}",
	f"-GPSLongitudeRef={'W' if lon_f < 0 else 'E'}",
]

if bearing:
	args.append(f"-GPSImgDirection={bearing}")
	args.append("-GPSImgDirectionRef=T")

print(" ".join(args), file=sys.stderr)
print("\n".join(args))
