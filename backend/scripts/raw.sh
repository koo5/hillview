set source_ext CR2
time for f in *.$source_ext; dcraw -T -w "$f" &; end; time wait
set final_ext tiff

#set final_ext webp
#for f in ./*.$source_ext; dcraw -T -w "$f" &; end; time wait

for f in *.CR2
	set final (string replace -r '\.CR2$' ".$final_ext" "$f")
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
