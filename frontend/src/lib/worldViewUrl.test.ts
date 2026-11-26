import { describe, expect, it } from 'vitest';
import { constructWorldShareUrl, parseWorldViewParams } from './worldViewUrl';

describe('3D view links', () => {
	it('round trips altitude and the direction and zoom of the camera, without unrelated view parameters', () => {
		const view = { lat: 50.1252096, lon: 14.4932864, altitude: 1250.75, bearing: 137, pitch: -18.5, fov: 12.25 };
		const url = new URL(constructWorldShareUrl('https://hillview.cz/?photo=old&x1=0.1&tx1=0.2', 20, view));
		expect(url.origin).toBe('https://hillview.cz');
		expect(Object.fromEntries(url.searchParams)).toEqual({
			activity: '3d', lat: '50.12520960', lon: '14.49328640', zoom: '20',
			altitude: '1250.75', bearing: '137.0000', pitch: '-18.5000', fov: '12.2500'
		});
		expect(parseWorldViewParams(url.searchParams)).toEqual({ altitude: 1250.75, pitch: -18.5, fov: 12.25 });
	});

	it('keeps defaults for old links and malformed camera parameters', () => {
		for (const query of ['', 'altitude=&pitch=&fov=', 'altitude=NaN&pitch=Infinity&fov=0', 'altitude=10m&pitch=91&fov=121']) {
			expect(parseWorldViewParams(new URLSearchParams(query))).toEqual({ altitude: undefined, pitch: -5, fov: 55 });
		}
	});

	it('accepts zero and negative absolute altitudes, and the zoom limits', () => {
		expect(parseWorldViewParams(new URLSearchParams('altitude=0&pitch=0&fov=0.1'))).toEqual({ altitude: 0, pitch: 0, fov: 0.1 });
		expect(parseWorldViewParams(new URLSearchParams('altitude=-100&pitch=-90&fov=120'))).toEqual({ altitude: -100, pitch: -90, fov: 120 });
	});
});
