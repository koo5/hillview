import { HILLVIEW_BASE_URL, constructUserProfileUrl } from './urlUtilsServer';

export interface PhotoSize {
	url: string;
	width: number;
	height: number;
	path?: string;
}

export interface PublicPhoto {
	id: string;
	uid: string;
	source?: string;
	original_filename: string | null;
	title?: string | null;
	description: string | null;
	keywords?: string[] | null;
	license?: string | null;
	is_public?: boolean;
	latitude: number | null;
	longitude: number | null;
	bearing: number | null;
	altitude?: number | null;
	width: number | null;
	height: number | null;
	captured_at: string | null;
	uploaded_at: string | null;
	processing_status?: string;
	sizes: Record<string, PhotoSize> | null;
	owner_id: string | null;
	owner_username: string | null;
	user_rating: 'thumbs_up' | 'thumbs_down' | null;
	rating_counts: { thumbs_up: number; thumbs_down: number };
	is_own_photo: boolean;
}

export interface PhotoAnnotation {
	id: string;
	photo_id?: string;
	user_id?: string;
	body: string | null;
	target?: unknown;
	owner_username: string | null;
	created_at: string | null;
	is_current?: boolean;
	event_type?: string;
}

export type AnnotationBodySegment =
	| { kind: 'text'; value: string }
	| { kind: 'link'; value: string };

export function getDisplayImageUrl(photo: { sizes: Record<string, PhotoSize> | null }): string {
	// Largest real variant up to 2048 — good quality without loading an 8192px
	// original for the detail <img>. Data-driven (see pickLargestImage).
	return pickLargestImage(photo, 2048)?.url ?? '';
}

// Non-display variants excluded from real-image selection:
//   *_crop — aspect-cropped social/grid thumbnails (320_crop, 1200_crop)
//   *_llm  — detection-masked image rendered for LLM analysis, never shown
function isDisplayVariant(key: string): boolean {
	return !key.includes('crop') && !key.includes('llm');
}

/**
 * Largest real (non-crop, non-llm) image variant whose width is <= maxWidth, by
 * actual stored dimensions — not a hardcoded key order. Falls back to the
 * smallest variant if every one exceeds the cap. Returns null if no sizes.
 *
 * Picks by actual dimensions rather than a curated key list, so it stays
 * correct no matter which keys a photo carries (the worker's set drifts across
 * versions), and the cap keeps us from handing an 8192px panorama to a crawler.
 */
export function pickLargestImage(
	photo: { sizes: Record<string, PhotoSize> | null },
	maxWidth = Infinity
): PhotoSize | null {
	if (!photo.sizes) return null;
	const variants = Object.entries(photo.sizes)
		.filter(([key, v]) => v && typeof v.width === 'number' && isDisplayVariant(key))
		.map(([, v]) => v);
	if (!variants.length) return null;
	const capped = variants.filter((v) => v.width <= maxWidth);
	const pool = capped.length ? capped : variants;
	return pool.reduce((best, v) => (v.width > best.width ? v : best));
}

/**
 * og:image selection. Prefers the 1.91:1 social-card crop (1200x630) the worker
 * makes for wide-enough images; otherwise the largest raw variant up to ~1280px
 * — the og:image sweet spot (≈1200 wide) without handing a scraper a multi-MB
 * original.
 *
 * Data-driven rather than a fixed key list because the worker's size set drifts
 * across versions — the photos table still holds legacy 1024/640/1600/50 keys
 * alongside current ones — so any hardcoded preference list silently rots (and a
 * planned full re-render will shift the set again).
 */
export function pickOgImage(
	photo: { sizes: Record<string, PhotoSize> | null }
): PhotoSize | null {
	return photo.sizes?.['1200_crop'] ?? pickLargestImage(photo, 1280);
}

/** Smallest variant by actual width — a real thumbnail. Null if no sizes.
 * Crops are fine thumbnails; the _llm analysis image is never shown, so skip it. */
export function pickSmallestImage(
	photo: { sizes: Record<string, PhotoSize> | null }
): PhotoSize | null {
	if (!photo.sizes) return null;
	const variants = Object.entries(photo.sizes)
		.filter(([key, v]) => v && typeof v.width === 'number' && !key.includes('llm'))
		.map(([, v]) => v);
	if (!variants.length) return null;
	return variants.reduce((best, v) => (v.width < best.width ? v : best));
}

/**
 * Builds a schema.org ImageObject for a public photo, suitable for a JSON-LD
 * <script>. Returns null when there's no photo. Fields we can't vouch for are
 * left undefined so JSON.stringify drops them.
 *
 * Kept a pure function (rather than inline in the page) so it can be unit-tested
 * against real API payloads.
 */
export function buildPhotoImageJsonLd(
	photo: PublicPhoto | null
): Record<string, unknown> | null {
	if (!photo) return null;
	// contentUrl: highest-res variant we'd hand a crawler (capped below 'full',
	// which can be 8192px for panoramas). thumbnailUrl: the smallest.
	const content = pickLargestImage(photo, 2048);
	const thumb = pickSmallestImage(photo);
	// Every Hillview photo carries governing terms — either a reusable license
	// (CC BY-SA + OSM) or 'arr' (all rights reserved, i.e. licensable only by
	// arranging it with the owner) — so all are eligible for the Licensable
	// badge, which needs `license`. The acquire path is what differs: a reusable
	// licence is free (follow the terms on /licensing), while 'arr' must be
	// negotiated via /contact.
	const license = photo.license || null;
	const isArr = license === 'arr';
	const licensePage = `${HILLVIEW_BASE_URL}/licensing`;
	const contactPage = `${HILLVIEW_BASE_URL}/contact`;
	return {
		'@context': 'https://schema.org',
		'@type': 'ImageObject',
		name: displayTitle(photo),
		description: photo.description || undefined,
		keywords: photo.keywords && photo.keywords.length ? photo.keywords : undefined,
		contentUrl: content?.url || undefined,
		thumbnailUrl: thumb?.url || undefined,
		width: content?.width || undefined,
		height: content?.height || undefined,
		dateCreated: photo.captured_at || undefined,
		datePublished: photo.uploaded_at || undefined,
		creator: photo.owner_username
			? {
					'@type': 'Person',
					name: photo.owner_username,
					url: photo.owner_id
						? `${HILLVIEW_BASE_URL}${constructUserProfileUrl(photo.owner_id)}`
						: undefined
				}
			: undefined,
		creditText: photo.owner_username || undefined,
		license: license ? licensePage : undefined,
		acquireLicensePage: license ? (isArr ? contactPage : licensePage) : undefined,
		contentLocation:
			photo.latitude != null && photo.longitude != null
				? {
						'@type': 'Place',
						geo: {
							'@type': 'GeoCoordinates',
							latitude: photo.latitude,
							longitude: photo.longitude
						}
					}
				: undefined
	};
}

export function displayTitle(photo: {
	title?: string | null;
	description?: string | null;
	original_filename: string | null;
}): string {
	return photo.title || photo.description || photo.original_filename || 'Photo';
}

export function parseAnnotationBody(body: string | null | undefined): AnnotationBodySegment[] {
	if (!body) return [];
	return body
		.split('|')
		.map((s) => s.trim())
		.filter((s) => s.length > 0)
		.map((s): AnnotationBodySegment =>
			/^https?:\/\//i.test(s) ? { kind: 'link', value: s } : { kind: 'text', value: s }
		);
}

export function formatDate(value: string | null | undefined): string {
	if (!value) return '';
	try {
		return new Date(value).toLocaleDateString();
	} catch {
		return value;
	}
}

export function formatDateTime(value: string | null | undefined): string {
	if (!value) return '';
	try {
		return new Date(value).toLocaleString();
	} catch {
		return value;
	}
}
