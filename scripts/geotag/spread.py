import os

raws = [f for f in os.listdir(".") if f.endswith(".CR2")]
start_bearing = 325
step = 360 / len(raws)

for i, raw in enumerate(raws):
	bearing = (start_bearing + i * step) % 360
	print(f"{raw}: {bearing:.2f}°")
	webp = 'opt/' + raw[:-4] + ".webp.opt.webp"

	os.system("""exiftool -TagsFromFile """ + raw + """ '-GPSImgDirectionRef=True North'   '-GPSLatitude*=50.12518006585093'   '-GPSLongitude*=14.518011069201226' '-GPSImgDirection*=""" + f"{bearing}' " + webp)

