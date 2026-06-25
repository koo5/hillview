import { describe, it, expect } from 'vitest';
import { convertPanoramaxItem } from './PanoramaxSourceLoader';

describe('convertPanoramaxItem', () => {
	const source = { id: 'panoramax', type: 'panoramax' };

	const baseItem = {
		id: 'ba7c08c3-6415-4044-9894-a8c1d0e59986',
		geometry: { type: 'Point', coordinates: [2.350131718, 48.860372804] },
		providers: [
			{ id: 'a6df9e3a-b94c-4980-b60e-23d0e7e88142', name: 'benoitdd', roles: ['producer'] }
		],
		properties: {
			datetime: '2025-07-17T19:44:20+00:00',
			'view:azimuth': 283,
			'geovisio:producer': 'benoitdd',
			license: 'CC-BY-SA-4.0'
		},
		assets: {
			thumb: { href: 'https://example.com/thumb.jpg' },
			sd: { href: 'https://example.com/sd.jpg' },
			hd: { href: 'https://example.com/hd.jpg' }
		}
	};

	it('builds uid from source.id + item.id', () => {
		const result = convertPanoramaxItem(baseItem, source);
		expect(result?.uid).toBe('panoramax-ba7c08c3-6415-4044-9894-a8c1d0e59986');
	});

	it('extracts coord from [lng, lat] geometry', () => {
		const result = convertPanoramaxItem(baseItem, source);
		expect(result?.coord).toEqual({ lat: 48.860372804, lng: 2.350131718 });
	});

	it('uses view:azimuth as bearing', () => {
		expect(convertPanoramaxItem(baseItem, source)?.bearing).toBe(283);
	});

	it('falls back to pers:yaw when view:azimuth missing', () => {
		const item = {
			...baseItem,
			properties: { ...baseItem.properties, 'view:azimuth': undefined, 'pers:yaw': 42 }
		};
		expect(convertPanoramaxItem(item, source)?.bearing).toBe(42);
	});

	it('defaults bearing to 0 when both heading fields missing', () => {
		const item = {
			...baseItem,
			properties: { ...baseItem.properties, 'view:azimuth': undefined }
		};
		expect(convertPanoramaxItem(item, source)?.bearing).toBe(0);
	});

	it('preserves CC-BY-SA-4.0 license verbatim', () => {
		expect((convertPanoramaxItem(baseItem, source) as any)?.license).toBe('CC-BY-SA-4.0');
	});

	it('extracts creator id and username from providers[role=producer]', () => {
		const creator = (convertPanoramaxItem(baseItem, source) as any)?.creator;
		expect(creator).toEqual({ id: 'a6df9e3a-b94c-4980-b60e-23d0e7e88142', username: 'benoitdd' });
	});

	it('falls back to geovisio:producer string when providers[] missing', () => {
		const item = { ...baseItem, providers: undefined };
		const creator = (convertPanoramaxItem(item, source) as any)?.creator;
		expect(creator).toEqual({ username: 'benoitdd' });
	});

	it('picks the producer entry over other roles', () => {
		const item = {
			...baseItem,
			providers: [
				{ id: 'host-id', name: 'host', roles: ['host'] },
				{ id: 'prod-id', name: 'real-producer', roles: ['producer'] }
			]
		};
		expect((convertPanoramaxItem(item, source) as any)?.creator).toEqual({
			id: 'prod-id',
			username: 'real-producer'
		});
	});

	it('populates sizes from STAC assets', () => {
		const result = convertPanoramaxItem(baseItem, source);
		expect(result?.sizes?.thumb?.url).toBe('https://example.com/thumb.jpg');
		expect(result?.sizes?.sd?.url).toBe('https://example.com/sd.jpg');
		expect(result?.sizes?.full?.url).toBe('https://example.com/hd.jpg');
	});

	it('parses datetime to numeric captured_at', () => {
		expect(convertPanoramaxItem(baseItem, source)?.captured_at).toBe(
			Date.parse('2025-07-17T19:44:20+00:00')
		);
	});

	it('returns null for malformed geometry', () => {
		expect(convertPanoramaxItem({ id: 'x', geometry: null }, source)).toBeNull();
		expect(convertPanoramaxItem({ id: 'x', geometry: { coordinates: [] } }, source)).toBeNull();
	});

	it('sets projection from pers:type property', () => {
		const item = {
			...baseItem,
			properties: { ...baseItem.properties, 'pers:type': 'equirectangular' }
		};
		expect((convertPanoramaxItem(item, source) as any)?.projection).toBe('equirectangular');
	});

	it('does not set projection when pers:type is absent', () => {
		const result = convertPanoramaxItem(baseItem, source);
		expect((result as any)?.projection).toBeUndefined();
	});

	it('preserves other pers:type values like perspective', () => {
		const item = {
			...baseItem,
			properties: { ...baseItem.properties, 'pers:type': 'perspective' }
		};
		expect((convertPanoramaxItem(item, source) as any)?.projection).toBe('perspective');
	});

	it('falls back to thumb url when hd asset missing', () => {
		const item = {
			...baseItem,
			assets: { thumb: { href: 'https://example.com/thumb.jpg' } }
		};
		expect(convertPanoramaxItem(item, source)?.url).toBe('https://example.com/thumb.jpg');
	});
});