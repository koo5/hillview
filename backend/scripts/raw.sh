for f in *.CR2
	set tiff (string replace -r '\.CR2$' '.tiff' "$f")
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
	  "$tiff" &
end
wait
