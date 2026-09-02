/**
 * OptimizedMarkerSystem.updateMarkers diffs against the markers already on the
 * map instead of rebuilding them all — the photo set is republished once per
 * source as it lands, and a rebuild per publish would flicker every marker.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { writable } from 'svelte/store';
import L from 'leaflet';

// happy-dom has no canvas 2D context, and the atlas paints one at import time.
vi.mock('./markerAtlas', () => ({
	arrowAtlas: {
		getDataUrl: () => 'data:image/png;base64,',
		getDimensions: () => ({ arrowSize: 24, width: 24 * 36, height: 24 }),
		getBackgroundPosition: () => '0px 0px'
	}
}));
vi.mock('$lib/data.svelte', () => ({ app: writable({ activity: 'navigation' }) }));
vi.mock('./mapState', () => ({ photoInFront: writable(null) }));

import { OptimizedMarkerSystem } from './optimizedMarkers';

const photo = (id: string, lat = 50.05, lng = 14.35, extra: Record<string, any> = {}) => ({
	id,
	uid: `hillview-${id}`,
	source_type: 'stream',
	filename: `${id}.jpg`,
	url: `https://x/${id}.jpg`,
	coord: { lat, lng },
	bearing: 90,
	altitude: 0,
	bearing_color: '#00ff00',
	source: { id: 'hillview', name: 'Hillview', type: 'stream', enabled: true, color: '#0a0' },
	...extra
}) as any;

describe('OptimizedMarkerSystem.updateMarkers (diffing)', () => {
	let map: L.Map;
	let system: OptimizedMarkerSystem;

	beforeEach(() => {
		const container = document.createElement('div');
		document.body.appendChild(container);
		map = L.map(container, { zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false }).setView([50.05, 14.35], 15);
		system = new OptimizedMarkerSystem({ enablePooling: true, maxPoolSize: 2000, enableSelection: true });
	});

	const markerFor = (markers: L.Marker[], id: string) =>
		markers.find(m => (m as any)._photoData?.id === id)!;

	it('keeps the marker object for a photo that survives a republish', () => {
		const first = system.updateMarkers(map, [photo('a'), photo('b')]);
		const aBefore = markerFor(first, 'a');
		const bBefore = markerFor(first, 'b');

		const second = system.updateMarkers(map, [photo('b'), photo('c')]);

		expect(markerFor(second, 'b')).toBe(bBefore);
		expect(map.hasLayer(bBefore)).toBe(true);
		// 'a' left the map (its pooled object may have been reused for 'c' — that's fine)
		const idsOnMap: string[] = [];
		map.eachLayer(l => { const id = (l as any)._photoData?.id; if (id) idsOnMap.push(id); });
		expect(idsOnMap.sort()).toEqual(['b', 'c']);
		expect(markerFor(second, 'c')).toBe(aBefore); // LIFO pool reuse
		expect(second).toHaveLength(2);
		expect(system.getStats().activeMarkers).toBe(2);
	});

	it('returns the array in the new photo order', () => {
		system.updateMarkers(map, [photo('a'), photo('b'), photo('c')]);
		const reordered = system.updateMarkers(map, [photo('c'), photo('a'), photo('b')]);
		expect(reordered.map(m => (m as any)._photoData.id)).toEqual(['c', 'a', 'b']);
	});

	it('moves a kept marker whose coordinates changed without rebuilding it', () => {
		const first = system.updateMarkers(map, [photo('a', 50.05, 14.35)]);
		const a = markerFor(first, 'a');
		const iconBefore = a.getIcon();

		system.updateMarkers(map, [photo('a', 50.06, 14.36)]);

		expect(a.getLatLng().lat).toBeCloseTo(50.06);
		expect(a.getIcon()).toBe(iconBefore);
	});

	it('rebuilds the icon only when a baked-in field changed', () => {
		const first = system.updateMarkers(map, [photo('a')]);
		const a = markerFor(first, 'a');
		const iconBefore = a.getIcon();

		// bearing-diff colour is patched in place …
		system.updateMarkers(map, [photo('a', 50.05, 14.35, { bearing_color: '#ff0000' })]);
		expect(a.getIcon()).toBe(iconBefore);
		const circle = a.getElement()!.querySelector('.bearing-circle') as HTMLElement;
		expect(circle.style.backgroundColor).toMatch(/#ff0000|rgb\(255, 0, 0\)/);

		// … a bearing change is a new arrow sprite, so the icon is rebuilt
		system.updateMarkers(map, [photo('a', 50.05, 14.35, { bearing: 180 })]);
		expect(a.getIcon()).not.toBe(iconBefore);
	});

	it('pools released markers and reuses them for later additions', () => {
		const first = system.updateMarkers(map, [photo('a')]);
		const a = markerFor(first, 'a');
		const pooledBefore = system.getStats().pooledMarkers;

		system.updateMarkers(map, []);
		expect(system.getStats().pooledMarkers).toBe(pooledBefore + 1);
		expect(system.getStats().activeMarkers).toBe(0);

		const again = system.updateMarkers(map, [photo('z')]);
		expect(markerFor(again, 'z')).toBe(a); // LIFO pool hands the same object back
	});

	it('a photo with no recorded heading draws grey with no arrow, and keeps it on colour updates', () => {
		const markers = system.updateMarkers(map, [photo('u', 50.05, 14.35, { has_bearing: false, bearing_color: '#00ff00' })]);
		const el = markerFor(markers, 'u').getElement()!;
		expect(el.querySelector('.direction-arrow')).toBeNull();
		const circle = el.querySelector('.bearing-circle') as HTMLElement;
		expect(circle.style.backgroundColor).toMatch(/#9e9e9e|rgb\(158, 158, 158\)/i);

		system.updateMarkerColors(markers, 90);
		expect(circle.style.backgroundColor).toMatch(/#9e9e9e|rgb\(158, 158, 158\)/i);
	});

	it('draws one marker for duplicate keys in a publish', () => {
		const markers = system.updateMarkers(map, [photo('a'), photo('a')]);
		expect(markers).toHaveLength(1);
		expect(system.getStats().activeMarkers).toBe(1);
	});

	it('the same id from two sources stays two markers', () => {
		const other = { ...photo('1'), uid: 'mapillary-1', source: { id: 'mapillary', name: 'Mapillary', type: 'stream', enabled: true } };
		const markers = system.updateMarkers(map, [photo('1'), other]);
		expect(markers).toHaveLength(2);
	});
});
