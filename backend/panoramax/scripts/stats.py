#!/usr/bin/env python3
"""What an instance serves: its ready collections and their items, then the
tombstoned collections it serves only on request. Base URL defaults to prod.

--report adds the size distribution, the contributors, and the collections
with the fewest and most items and the most recently updated ones (what the
next incremental harvest fetches), each with a link into an explorer: a
meta-catalog's web viewer that harvests the instance."""

import argparse, json, urllib.parse, urllib.request
from collections import defaultdict
from datetime import datetime

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('base', nargs='?', default='https://p1.geovisio.hillview.cz', help='instance base URL, without /api')
ap.add_argument('--report', action='store_true', help='list collections and contributors, not just totals')
ap.add_argument('--top', type=int, default=5, help='collections per list (default 5)')
ap.add_argument('--explorer', default='https://explore.dev4-2.jj.internal', help='explorer the links point at')
args = ap.parse_args()


def get(url):
	return json.load(urllib.request.urlopen(url))


collections, n, url = [], 0, f'{args.base}/api/collections?limit=100'
while url:
	d = get(url);
	collections += d['collections'];
	n += sum(c['stats:items']['count'] for c in d['collections'])
	url = next((l['href'] for l in d['links'] if l['rel'] == 'next'), None)
	if not args.report:
		print(len(collections), 'collections,', n, 'items, next: ', url)

url, t = f'{args.base}/api/collections?limit=1000&filter=' + urllib.parse.quote("status='deleted'"), 0
while url:
	d = get(url);
	t += len(d['collections']);
	url = next((l['href'] for l in d['links'] if l['rel'] == 'next'), None)
if args.report:
	print(len(collections), 'collections,', n, 'items')
print(t, "tombstoned collections served on request (filter status='deleted')")

if not args.report:
	raise SystemExit


def count(c):
	return c['stats:items']['count']


def owner(c):
	return ', '.join(p['name'] for p in c.get('providers', [])) or '?'


def span(c):
	start, end = c['extent']['temporal']['interval'][0]
	if start is None or end is None:
		return 'no capture time'
	minutes = round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60)
	return f"{start[:16].replace('T', ' ')} +{minutes} min"


def link(c):
	# The explorer opens a collection through one of its pictures; the first
	# one also gives the map a place to start.
	features = get(f"{args.base}/api/collections/{c['id']}/items?limit=1")['features']
	if not features:
		return f"(no items) {args.base}/api/collections/{c['id']}"
	f = features[0]
	lon, lat = f['geometry']['coordinates']
	return f"{args.explorer}/en/index?focus=map&map=18/{lat}/{lon}&pic={f['id']}&seq={c['id']}"


def listing(title, rows):
	print(f'\n{title}')
	for c in rows:
		print(f'  {count(c):>6}  {owner(c):<20}  {span(c):<26}  {link(c)}')


print('\nCollection sizes')
for lo, hi in [(1, 1), (2, 9), (10, 99), (100, 999), (1000, None)]:
	sized = [c for c in collections if count(c) >= lo and (hi is None or count(c) <= hi)]
	label = str(lo) if lo == hi else f'{lo}+' if hi is None else f'{lo}–{hi}'
	print(f'  {label:>8} items: {len(sized):>5} collections, {sum(map(count, sized)):>7} items')

print('\nContributors')
by = defaultdict(lambda: [0, 0])
for c in collections:
	by[owner(c)][0] += 1
	by[owner(c)][1] += count(c)
for name, (cs, items) in sorted(by.items(), key=lambda kv: -kv[1][1]):
	print(f'  {name:<20} {cs:>5} collections, {items:>7} items')

by_size = sorted(collections, key=lambda c: (count(c), c['id']))
listing(f'Fewest items (of {sum(count(c) == count(by_size[0]) for c in collections)} with {count(by_size[0])})', by_size[:args.top])
listing('Most items', by_size[::-1][:args.top])
listing('Most recently updated', sorted(collections, key=lambda c: c['updated'], reverse=True)[:args.top])
