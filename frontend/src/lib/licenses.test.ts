import { describe, expect, it } from 'vitest';
import { photoUploadConsent, publishedLicense, uploadGrant, needsPanoramaxLicenseChoice } from './licenses';

describe('contextual sharing consent', () => {
	it.each([
		['ccbysa4+osm', true, true], ['ccbysa4+osm', false, false],
		['full1', true, false], ['panoramax_in', true, false],
		[null, true, false], [undefined, true, false]
	])('requires a license choice for %s, sharing=%s: %s', (license, sharing, expected) => {
		expect(needsPanoramaxLicenseChoice(license as string | null | undefined, sharing as boolean)).toBe(expected);
	});
});

describe('upload grants and public licenses', () => {
	it.each([
		['full1', false, 'arr'], ['full1', true, 'panoramax'],
		['panoramax_in', false, 'panoramax'], ['panoramax_in', true, 'panoramax'],
		['ccbysa4+osm', false, 'ccbysa4+osm'], ['ccbysa4+osm', true, 'ccbysa4+osm'],
		[null, true, null]
	])('publishes %s with sharing=%s as %s', (grant, sharing, expected) => {
		expect(publishedLicense(grant as string | null, sharing as boolean)).toBe(expected);
	});
	it('never guesses which intake produced a Panoramax publication', () => {
		expect(uploadGrant(undefined, 'panoramax')).toBeNull();
		expect(uploadGrant('full1', 'panoramax')).toBe('full1');
		expect(uploadGrant('panoramax_in', 'panoramax')).toBe('panoramax_in');
		expect(uploadGrant(undefined, 'arr')).toBe('full1');
	});
});

describe('captured upload consent', () => {
	it('preserves an explicit capture choice when defaults later change', () => {
		expect(photoUploadConsent({ license: 'panoramax_in', panoramax_share: false }, 'full1'))
			.toEqual({ license: 'panoramax_in', panoramax_share: false });
		expect(photoUploadConsent({ license: 'full1', panoramax_share: true }, 'ccbysa4+osm'))
			.toEqual({ license: 'full1', panoramax_share: true });
	});
	it('lets legacy and pre-choice photos adopt a grant without inventing sharing consent', () => {
		expect(photoUploadConsent({}, 'full1')).toEqual({ license: 'full1', panoramax_share: false });
		expect(photoUploadConsent({ license: null, panoramax_share: true }, 'full1'))
			.toEqual({ license: 'full1', panoramax_share: true });
	});
	it('refuses upload when no grant has been chosen', () => {
		expect(() => photoUploadConsent({ panoramax_share: true }, null)).toThrow('Choose an upload license');
	});
});
