#!/usr/bin/env fish

for f in *.CR2
	set final (string replace -r '\.CR2$' ".webp" "webp/$f")
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
	  "$final" &
end
time wait
