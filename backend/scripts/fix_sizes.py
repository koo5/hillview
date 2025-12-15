#!/usr/bin/env python3

import sys,json
photos = json.loads(open(sys.argv[1], 'r').read())
fixed_count = 0
for photo in photos:
	sizes = photo.get('sizes')
	if sizes == None:
		#print(f"Photo {photo['id']} has no sizes, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	s320 = sizes.get('320')
	if s320 == None:
		print(f"Photo {photo['id']} missing size 320, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	sfull = sizes.get('full')
	if sfull == None:
		print(f"Photo {photo['id']} missing size full, skipping")
		#print(json.dumps(photo, indent=2))
		continue

	if s320['width'] > s320['height']:
		if sfull['width'] < sfull['height']:
			#print(f"Photo {photo['id']} has mismatched sizes, fixing full size")
			#fixed_count += 1
			#print(json.dumps(photo['record_created_ts'], indent=2))
			#print(json.dumps(photo, indent=2))
			fixed_sizes = sizes.copy()
			h = sfull['height']
			w = sfull['width']
			fixed_sizes['full']['width'] = h
			fixed_sizes['full']['height'] = w
			print(f"""UPDATE photos SET width = {w}, height = {h}, sizes = '{json.dumps(fixed_sizes)}' WHERE id = '{photo['id']}';""")
			fixed_count += 1
