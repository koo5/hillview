#!/usr/bin/env fish

for f in *.CR2
	set final (string replace -r '\.CR2$' ".webp" "webp/$f")
	set stem (string replace -r '\.CR2$' '' "$f")
	# rawtherapee-cli emits .tif, but darktable-cli (and older runs) may emit
	# .tiff — match raw.py's find_tiff() and prefer .tiff.
	set tiff "tiff/$stem.tiff"
	if not test -f "$tiff"
		set tiff "tiff/$stem.tif"
	end
	begin
		exiftool -overwrite_original -TagsFromFile "$f" \
		  '-EXIF:all' \
		  '-GPS:all' \
		  '-XMP:all' \
		  '-IPTC:all' \
		  '-MakerNotes=' \
		  '-ThumbnailImage=' \
		  '-PreviewImage=' \
		  '-EXIF:PixelXDimension=' \
		  '-EXIF:PixelYDimension=' \
		  '-GPS:GPSDateStamp=' \
		  "$final"
		# Mirror Orientation from the upstream TIFF the webp was made from.
		# RawTherapee outputs upside-down pixels with Orient=3; darktable
		# physically rotates and tags =1. Reading from whichever TIFF actually
		# exists self-corrects, so a dir that mixes both pipelines (e.g.
		# pano-prep'd dirs that get re-run through raw.sh) gets the right tag
		# per file. -EXIF:all above already clobbered the webp's Orient with
		# the CR2's value, so this re-applies the correct one.
		#
		# -n (numeric): on WebP containers exiftool silently no-ops a
		# string-form Orientation write while still reporting success — the
		# bug that hid the previous "force =1" for four weeks.
		if test -f "$tiff"
			exiftool -overwrite_original -n -TagsFromFile "$tiff" -Orientation "$final"
		else
			echo "warning: $tiff missing; webp Orient inherits CR2's (likely wrong)" >&2
		end
	end &
end
time wait
