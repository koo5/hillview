#!/usr/bin/env fish

mkdir tiff; mkdir webp; mkdir webp_noanon;

for f in ./*.CR2
	# skip if the tiff already exists
	set tiff (string replace -r '\.CR2$' '\.tiff' "tiff/$f")
	if test -f $tiff
		continue
	end
	set jobs (count (jobs -p))
    while test $jobs -ge 20; echo "Waiting for jobs to finish... ($jobs running)"; sleep 1; set jobs (count (jobs -p)); end
    dcraw -T -w "$f" &
    mv (string replace -r '\.CR2$' '\.tiff' "$f") "tiff/"
end
time wait
#mv *.tiff tiff/
set profile -preset photo -q 98# -m 6 -af -metadata all
for f in ./*.CR2
	set jobs (count (jobs -p))
    while test $jobs -ge 20; echo "Waiting for jobs to finish... ($jobs running)"; sleep 1; set jobs (count (jobs -p)); end
    cwebp $profile (string replace -r '\.CR2$' '.tiff' "tiff/$f") -o (string replace -r '\.CR2$' '.webp' "webp/$f") &
end
time wait

