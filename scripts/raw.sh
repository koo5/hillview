#!/usr/bin/env fish

mkdir tiff; mkdir webp; mkdir webp_noanon;

for f in ./*.CR2; dcraw -T -w "$f" &; end; time wait
mv *.tiff tiff/
for f in ./*.CR2; cwebp -lossless (string replace -r '\.CR2$' '.tiff' "$f") -o (string replace -r '\.CR2$' '.webp' "webp/$f") &; end; 
time wait

