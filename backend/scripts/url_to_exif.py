#!/usr/bin/env python3
"""Extract lat, lon, bearing from a Hillview URL and output exiftool arguments.

Usage:
    ./url_to_exif.py 'https://hillview.cz/?lat=50.17&lon=14.46&bearing=77.87'
    exiftool $(./url_to_exif.py 'URL') photo.tif
"""

import sys
from urllib.parse import urlparse, parse_qs

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} '<hillview-url>'", file=sys.stderr)
    sys.exit(1)

params = parse_qs(urlparse(sys.argv[1]).query)

lat = params.get("lat", [None])[0]
lon = params.get("lon", [None])[0]
bearing = params.get("bearing", [None])[0]

if not lat or not lon:
    print("Error: could not extract lat/lon from URL", file=sys.stderr)
    sys.exit(1)

lat_f = float(lat)
lon_f = float(lon)

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
