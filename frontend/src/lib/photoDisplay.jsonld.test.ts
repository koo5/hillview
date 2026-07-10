import { describe, it, expect } from 'vitest';
import { buildPhotoImageJsonLd, pickOgImage, type PublicPhoto } from './photoDisplay';
import { serializeJsonLd } from './jsonld';

// A real /api/photos/public/<uid> payload (captured from a prod-data copy):
// an all-rights-reserved panorama, no description, owned by 'test'.
const REAL_PHOTO = {
	id: 'f05d913a-0b1e-4276-aded-d61aaa9a77af',
	uid: 'hillview-f05d913a-0b1e-4276-aded-d61aaa9a77af',
	source: 'hillview',
	original_filename: '2026-05-11_100EOS5D_AAAB6107.tif',
	description: null,
	license: 'arr',
	latitude: 50.05299,
	longitude: 14.542728,
	bearing: 257.81,
	width: 8726,
	height: 5840,
	captured_at: '2026-05-11T11:34:14Z',
	uploaded_at: '2026-06-12T20:51:41.444796Z',
	owner_id: 'badb7364-efc7-437f-90be-9622841c5f45',
	owner_username: 'test',
	sizes: {
		full: { width: 8192, height: 5482, url: 'https://h/opt/full/x.webp' },
		'320': { width: 320, height: 214, url: 'https://h/opt/320/x.webp' },
		'1200': { width: 1200, height: 803, url: 'https://h/opt/1200/x.webp' },
		'2048': { width: 2048, height: 1370, url: 'https://h/opt/2048/x.webp' },
		'320_crop': { width: 320, height: 240, url: 'https://h/opt/320_crop/x.webp' }
	},
	user_rating: null,
	rating_counts: { thumbs_up: 0, thumbs_down: 0 },
	is_own_photo: false
} as unknown as PublicPhoto;

describe('buildPhotoImageJsonLd', () => {
	it('returns null when there is no photo', () => {
		expect(buildPhotoImageJsonLd(null)).toBeNull();
	});

	it('builds an ImageObject from a real payload', () => {
		const ld = buildPhotoImageJsonLd(REAL_PHOTO)!;
		expect(ld['@context']).toBe('https://schema.org');
		expect(ld['@type']).toBe('ImageObject');
		// name falls back to filename (no description/title yet)
		expect(ld.name).toBe('2026-05-11_100EOS5D_AAAB6107.tif');
		expect(ld.description).toBeUndefined();
	});

	it('picks the largest variant <= 2048 for contentUrl (not the 8192 full)', () => {
		const ld = buildPhotoImageJsonLd(REAL_PHOTO)!;
		expect(ld.contentUrl).toBe('https://h/opt/2048/x.webp');
		expect(ld.width).toBe(2048);
		expect(ld.height).toBe(1370);
	});

	it('picks a small, non-crop variant for thumbnailUrl', () => {
		const ld = buildPhotoImageJsonLd(REAL_PHOTO)!;
		expect(ld.thumbnailUrl).toBe('https://h/opt/320/x.webp');
	});

	it('all-rights-reserved (arr): licensable by arrangement — acquire via /contact', () => {
		const ld = buildPhotoImageJsonLd(REAL_PHOTO)!;
		expect(ld.license).toBe('https://hillview.cz/licensing');
		expect(ld.acquireLicensePage).toBe('https://hillview.cz/contact');
	});

	it('reusable license (CC): free to use — acquire via /licensing', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, license: 'ccbysa4+osm' })!;
		expect(ld.license).toBe('https://hillview.cz/licensing');
		expect(ld.acquireLicensePage).toBe('https://hillview.cz/licensing');
	});

	it('includes geo and a creator with an absolute profile URL', () => {
		const ld = buildPhotoImageJsonLd(REAL_PHOTO)!;
		expect(ld.contentLocation).toEqual({
			'@type': 'Place',
			geo: { '@type': 'GeoCoordinates', latitude: 50.05299, longitude: 14.542728 }
		});
		expect(ld.creator).toEqual({
			'@type': 'Person',
			name: 'test',
			url: 'https://hillview.cz/users/badb7364-efc7-437f-90be-9622841c5f45'
		});
		expect(ld.creditText).toBe('test');
	});

	it('omits geo when coordinates are absent', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, latitude: null, longitude: null })!;
		expect(ld.contentLocation).toBeUndefined();
	});

	it('puts the reverse-geocoded place name into contentLocation', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, place_name: 'Prosek, Praha' })!;
		expect(ld.contentLocation).toEqual({
			'@type': 'Place',
			name: 'Prosek, Praha',
			geo: { '@type': 'GeoCoordinates', latitude: 50.05299, longitude: 14.542728 }
		});
	});

	it('emits a name-only Place when geocoded but coordinates are missing', () => {
		const ld = buildPhotoImageJsonLd({
			...REAL_PHOTO, latitude: null, longitude: null, place_name: 'Prosek, Praha'
		})!;
		expect(ld.contentLocation).toEqual({ '@type': 'Place', name: 'Prosek, Praha' });
	});

	it('surfaces a description when present', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, description: 'Panorama Prahy z Grebovky' })!;
		// name still falls back to filename (no title); description is its own field
		expect(ld.description).toBe('Panorama Prahy z Grebovky');
	});

	it('prefers title for name, keeping description separate', () => {
		const ld = buildPhotoImageJsonLd({
			...REAL_PHOTO,
			title: 'Grébovka',
			description: 'Panorama Prahy z Grébovky'
		})!;
		expect(ld.name).toBe('Grébovka');
		expect(ld.description).toBe('Panorama Prahy z Grébovky');
	});

	it('emits a copyright notice: taken-year + owner, "All rights reserved." for arr', () => {
		// REAL_PHOTO is arr, captured 2026, owned by 'test'
		expect(buildPhotoImageJsonLd(REAL_PHOTO)!.copyrightNotice).toBe(
			'© 2026 test. All rights reserved.'
		);
	});

	it('omits "All rights reserved." for a CC-licensed photo (copyright is not waived)', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, license: 'ccbysa4+osm' })!;
		expect(ld.copyrightNotice).toBe('© 2026 test');
	});

	it('falls back to the upload year when there is no taken date', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, captured_at: null })!;
		// uploaded_at is 2026-06-12
		expect(ld.copyrightNotice).toBe('© 2026 test. All rights reserved.');
	});

	it('drops the year when neither date is known, keeping the holder', () => {
		const ld = buildPhotoImageJsonLd({
			...REAL_PHOTO, license: 'ccbysa4+osm', captured_at: null, uploaded_at: null
		})!;
		expect(ld.copyrightNotice).toBe('© test');
	});

	it('omits copyrightNotice entirely for an ownerless photo', () => {
		const ld = buildPhotoImageJsonLd({ ...REAL_PHOTO, owner_username: null })!;
		expect(ld.copyrightNotice).toBeUndefined();
	});

	it('emits keywords when present, omits them when empty', () => {
		const withKw = buildPhotoImageJsonLd({
			...REAL_PHOTO,
			keywords: ['Gröbovka', 'Havlíčkovy sady']
		})!;
		expect(withKw.keywords).toEqual(['Gröbovka', 'Havlíčkovy sady']);
		expect(buildPhotoImageJsonLd({ ...REAL_PHOTO, keywords: [] })!.keywords).toBeUndefined();
		expect(buildPhotoImageJsonLd(REAL_PHOTO)!.keywords).toBeUndefined();
	});
});

describe('pickOgImage', () => {
	it('falls back to a ~1200 raw size (not the 320 crop or 8192 full) when no 1.91:1 crop exists', () => {
		// REAL_PHOTO is not wide enough for a 1200_crop, so OG lands on 1200.
		const og = pickOgImage(REAL_PHOTO);
		expect(og?.url).toBe('https://h/opt/1200/x.webp');
		expect(og?.width).toBe(1200);
	});

	it('prefers the 1.91:1 crop when it exists', () => {
		const wide = {
			...REAL_PHOTO,
			sizes: {
				...REAL_PHOTO.sizes,
				'1200_crop': { width: 1200, height: 630, url: 'https://h/opt/1200_crop/x.webp' }
			}
		} as unknown as PublicPhoto;
		expect(pickOgImage(wide)?.url).toBe('https://h/opt/1200_crop/x.webp');
	});

	it('never selects the detection-masked _llm variant', () => {
		const withLlm = {
			...REAL_PHOTO,
			sizes: {
				'640_llm': { width: 640, height: 427, url: 'https://h/opt/640_llm/x.webp' },
				'320': { width: 320, height: 214, url: 'https://h/opt/320/x.webp' }
			}
		} as unknown as PublicPhoto;
		// largest non-llm variant is 320, not the 640_llm analysis image
		expect(pickOgImage(withLlm)?.url).toBe('https://h/opt/320/x.webp');
	});

	it('uses a legacy size (1024) for older photos that never got a 1200 variant', () => {
		// ~10k photos predate the 1200 variant; OG must not skip to 8192 'full'.
		const legacy = {
			...REAL_PHOTO,
			sizes: {
				full: { width: 8192, height: 5482, url: 'https://h/opt/full/x.webp' },
				'1024': { width: 1024, height: 683, url: 'https://h/opt/1024/x.webp' },
				'640': { width: 640, height: 427, url: 'https://h/opt/640/x.webp' },
				'320': { width: 320, height: 214, url: 'https://h/opt/320/x.webp' }
			}
		} as unknown as PublicPhoto;
		expect(pickOgImage(legacy)?.url).toBe('https://h/opt/1024/x.webp');
	});
});

describe('serializeJsonLd', () => {
	it('escapes < so a malicious string cannot break out of the script tag', () => {
		const out = serializeJsonLd({ description: '</script><img src=x onerror=alert(1)>' });
		expect(out).not.toContain('</script>');
		expect(out).not.toContain('<img');
		// still valid JSON that parses back to the original string
		expect(JSON.parse(out).description).toBe('</script><img src=x onerror=alert(1)>');
	});
});
