import { describe, it, expect } from 'vitest';
import { convertPanoramaxItem, isOwnInstanceItem } from './PanoramaxSourceLoader';

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

	it('sets projection to equirectangular from GPano XMP projection type', () => {
		const item = {
			...baseItem,
			properties: {
				...baseItem.properties,
				exif: { 'Xmp.GPano.ProjectionType': 'equirectangular' }
			}
		};
		expect((convertPanoramaxItem(item, source) as any)?.projection).toBe('equirectangular');
	});

	it('sets projection to equirectangular from 360° field-of-view', () => {
		const item = {
			...baseItem,
			properties: {
				...baseItem.properties,
				'pers:interior_orientation': { field_of_view: 360 }
			}
		};
		expect((convertPanoramaxItem(item, source) as any)?.projection).toBe('equirectangular');
	});

	it('does not set projection for flat photos', () => {
		const item = {
			...baseItem,
			properties: {
				...baseItem.properties,
				'pers:interior_orientation': { field_of_view: 72 }
			}
		};
		expect((convertPanoramaxItem(item, source) as any)?.projection).toBeUndefined();
	});

	it('does not set projection when no 360° signal is present', () => {
		const result = convertPanoramaxItem(baseItem, source);
		expect((result as any)?.projection).toBeUndefined();
	});

	it('falls back to thumb url when hd asset missing', () => {
		const item = {
			...baseItem,
			assets: { thumb: { href: 'https://example.com/thumb.jpg' } }
		};
		expect(convertPanoramaxItem(item, source)?.url).toBe('https://example.com/thumb.jpg');
	});
});
describe('isOwnInstanceItem', () => {
	const foreignItem = {
		id: 'ba7c08c3-6415-4044-9894-a8c1d0e59986',
		links: [
			{ rel: 'via', href: 'https://panoramax.openstreetmap.fr', type: 'application/json' }
		],
		assets: {
			hd: { href: 'https://panoramax.openstreetmap.fr/api/pictures/x/hd.jpg' }
		}
	};

	it('keeps items whose via link points at a foreign instance', () => {
		expect(isOwnInstanceItem(foreignItem)).toBe(false);
	});

	it('drops items whose via link points at our instance', () => {
		const item = {
			...foreignItem,
			links: [{ rel: 'via', href: 'https://panoramax.hillview.cz', instance_name: 'hillview' }]
		};
		expect(isOwnInstanceItem(item)).toBe(true);
	});

	it('matches via hrefs regardless of trailing slash and case', () => {
		const item = {
			...foreignItem,
			links: [{ rel: 'via', href: 'https://Panoramax.Hillview.CZ/' }]
		};
		expect(isOwnInstanceItem(item)).toBe(true);
	});

	it('does not treat a foreign host merely containing our prefix as ours', () => {
		const item = {
			...foreignItem,
			links: [{ rel: 'via', href: 'https://panoramax.hillview.cz.evil.example' }]
		};
		expect(isOwnInstanceItem(item)).toBe(false);
	});

	it('via link is authoritative: no asset fallback when via is present', () => {
		// foreign via + our asset host: trust the via link
		const item = {
			...foreignItem,
			links: [{ rel: 'via', href: 'https://panoramax.openstreetmap.fr' }],
			assets: { hd: { href: 'https://pics.hillview.cz/opt/2048/u/p.webp' } }
		};
		expect(isOwnInstanceItem(item)).toBe(false);
	});

	it('falls back to asset-URL prefixes when no via link exists', () => {
		const item = {
			id: 'x',
			assets: { hd: { href: 'https://pics.hillview.cz/opt/2048/u/p.webp' } }
		};
		expect(isOwnInstanceItem(item)).toBe(true);
	});

	it('asset fallback recognizes every configured pics/CDN host', () => {
		for (const prefix of [
			'https://pics.hillview.cz/',
			'https://pics2.hillview.cz/',
			'https://pics4.t3.storage.dev/'
		]) {
			const item = { id: 'x', assets: { thumb: { href: `${prefix}opt/640/u/p.webp` } } };
			expect(isOwnInstanceItem(item)).toBe(true);
		}
	});

	it('keeps items with neither via link nor recognizable assets', () => {
		const item = {
			id: 'x',
			assets: { hd: { href: 'https://cdn.elsewhere.example/p.jpg' } }
		};
		expect(isOwnInstanceItem(item)).toBe(false);
	});

	it('tolerates items with no links and no assets', () => {
		expect(isOwnInstanceItem({ id: 'x' })).toBe(false);
	});
});
