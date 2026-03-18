#!/usr/bin/env fish

set DIR (dirname (readlink -m (status --current-filename)))
mkdir tiff; mkdir webp; mkdir webp_noanon;

for f in *.CR2
	# skip if the tiff already exists
	set tiff (string replace -r '\.CR2$' '\.tiff' "tiff/$f")
	if test -f $tiff
		continue
	end
	set jobs (count (jobs -p))
	while test $jobs -ge 20
		echo "Waiting for jobs to finish... ($jobs running)";
		sleep 1;
		set jobs (count (jobs -p));
	end
	set tiff_name (string replace -r '\.CR2$' '.tiff' "$f")
	echo "[$(date)] Starting processing $f... ($jobs running)"
	set cmd "rawtherapee-cli -p '/usr/share/rawtherapee/profiles/Auto-Matched Curve - ISO Low.pp3' -o tiff/"(string escape -- $tiff_name)" -tz -c "(string escape -- $f)
	echo "[$(date)] Running command: $cmd"
	eval $cmd &
end
time wait
#mv *.tiff tiff/
set profile -preset photo -q 98# -m 6 -af -metadata all
for f in ./*.CR2
	if test -f (string replace -r '\.CR2$' '.webp' "webp/$f")
		continue
	end
	set jobs (count (jobs -p))
	while test $jobs -ge 20; echo "Waiting for jobs to finish... ($jobs running)"; sleep 1; set jobs (count (jobs -p)); end
	cwebp $profile (string replace -r '\.CR2$' '.tiff' "tiff/$f") -o (string replace -r '\.CR2$' '.webp' "webp/$f") &
end
time wait

$DIR/exif_tags_from_cr2_to_webp.sh
uv run $DIR/geotag/geo_tag.py $argv
