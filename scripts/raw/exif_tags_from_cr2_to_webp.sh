#!/usr/bin/env fish

for f in *.CR2
	set final (string replace -r '\.CR2$' ".webp" "webp/$f")
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
		# RawTherapee (with our `Auto-Matched Curve - ISO Low.pp3` profile)
		# emits TIFFs whose pixels are rotated 180° from upright, regardless
		# of whether the source CR2 was landscape (Orient=1) or portrait
		# (Orient=6/8). RT compensates by tagging its output Orientation=3
		# ("Rotate 180"), and cwebp carries that through. The -EXIF:all step
		# above then helpfully overwrites Orient=3 with the CR2's Orient=1/6/8,
		# breaking the compensation — landscapes show upside-down, portraits
		# display sideways or upside-down. Re-force =3 in a separate pass to
		# undo that.
		#
		# -n (numeric) matters: on WebP containers exiftool will silently
		# no-op a string-form "=3" while still reporting "1 image files
		# updated". That mis-PrintConv is exactly how the previous attempt
		# (`-Orientation=1` baked into the same call) hid for four weeks.
		exiftool -overwrite_original -n -Orientation=3 "$final"
	end &
end
time wait
