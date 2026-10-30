/** Upload grants, in broadest-to-narrowest permission to Hillview order.
 * These are distinct from the public license returned on photo reads. */
export const UPLOAD_LICENSES = [
	{
		id: 'full1',
		label: 'Full rights to Hillview',
		summary: 'Give Hillview full reuse rights, including commercial use.',
		explainer: 'You keep your copyright and grant Hillview full rights to the photo, including paid tiers later. With Panoramax sharing on, Hillview publishes it as Panoramax. With sharing off, it publishes as all rights reserved plus the OpenStreetMap mapping grant. Choose this to support the project.'
	},
	{
		id: 'panoramax_in',
		label: 'Panoramax contribution grant',
		summary: 'Allow Panoramax-compatible publication. Final license wording is pending.',
		explainer: 'You keep your copyright and permit Hillview to publish under a Panoramax-compatible license. The final license wording is pending. The photo is published as Panoramax even with sharing off. Turn on sharing separately to offer it to the federation.'
	},
	{
		id: 'ccbysa4+osm',
		label: 'CC BY-SA 4.0 + OSM mapping grant',
		summary: 'Allow public reuse with attribution and share-alike, plus OSM mapping.',
		explainer: 'You keep your copyright. Anyone may copy, share and remix the photo, commercially too, with attribution and share-alike. OpenStreetMap mappers may also trace map data from it into OSM. This grant alone does not cover Panoramax federation’s derived-data uses.'
	}
] as const;

export function canGrantPanoramax(license: string | null | undefined): boolean {
	return license === 'full1' || license === 'panoramax_in';
}

/** An unset grant may record a future preference; uploads still need a grant. */
export function needsPanoramaxLicenseChoice(license: string | null | undefined, sharing: boolean): boolean {
	return sharing && !!license && !canGrantPanoramax(license);
}

export function publishedLicense(grant: string | null | undefined, sharing: boolean): string | null {
	if (!grant) return null;
	if (grant === 'panoramax_in' || (grant === 'full1' && sharing)) return 'panoramax';
	return grant === 'full1' ? 'arr' : grant;
}

/** A Panoramax read value is ambiguous: it may come from either intake grant.
 * Never guess an intake grant for an edit from that public value. */
export function uploadGrant(granted: string | null | undefined, published?: string | null): string | null {
	if (UPLOAD_LICENSES.some(option => option.id === granted)) return granted!;
	if (published === 'arr') return 'full1';
	if (UPLOAD_LICENSES.some(option => option.id === published)) return published!;
	return null;
}

/** Shared by foreground and service-worker uploaders. Legacy / pre-choice
 * captures adopt the upload setting; absent sharing always means off. */
export function photoUploadConsent(
	photo: { license?: string | null; panoramax_share?: boolean },
	defaultLicense: string | null | undefined
): { license: string; panoramax_share: boolean } {
	const license = photo.license ?? defaultLicense;
	if (!license) throw new Error('Choose an upload license before uploading');
	return { license, panoramax_share: photo.panoramax_share ?? false };
}
