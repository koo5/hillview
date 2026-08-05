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
	place_name?: string | null;
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
 * Human-readable copyright notice for the ImageObject's `copyrightNotice` — the
 * field Google's Image Metadata report flags when absent. Names the owner and,
 * when a date is known, the year (taken date, falling back to upload date).
 *
 * Every Hillview photo stays under its owner's copyright: 'arr' reserves all
 * rights, and CC BY-SA *licenses* the photo without waiving copyright — so a '©'
 * notice is correct for both. Only 'arr' gets the "All rights reserved." tail;
 * appending it to a CC photo would contradict the licence it grants.
 *
 * Returns undefined for an ownerless photo (owner_username null) so
 * JSON.stringify drops the field rather than emitting a holder-less '©'.
 */
export function buildCopyrightNotice(photo: {
	owner_username: string | null;
	license?: string | null;
	captured_at?: string | null;
	uploaded_at?: string | null;
}): string | undefined {
	if (!photo.owner_username) return undefined;
	const stamp = photo.captured_at || photo.uploaded_at;
	const year = stamp ? new Date(stamp).getUTCFullYear() : NaN;
	const holder = Number.isNaN(year)
		? `© ${photo.owner_username}`
		: `© ${year} ${photo.owner_username}`;
	return photo.license === 'arr' ? `${holder}. All rights reserved.` : holder;
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
	photo: PublicPhoto | null,
	annotations: PhotoAnnotation[] = []
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
	const hasGeo = photo.latitude != null && photo.longitude != null;
	// schema.org Place: the reverse-geocoded place name plus the coordinates of
	// where the photo was taken. Either part may be absent.
	const place =
		photo.place_name || hasGeo
			? {
					'@type': 'Place',
					name: photo.place_name || undefined,
					geo: hasGeo
						? { '@type': 'GeoCoordinates', latitude: photo.latitude, longitude: photo.longitude }
						: undefined
				}
			: undefined;
	// keywords: any curator-set keywords, plus the distinct landmark labels the
	// annotations name — deduped case-insensitively across both. These describe
	// what's actually in the frame (a topical/geographic signal for the image),
	// so a densely-annotated Prague pano reads unambiguously as a view *of Prague*.
	const keywords = dedupeCaseInsensitive([
		...(photo.keywords ?? []),
		...annotationKeywords(annotations)
	]);
	return {
		'@context': 'https://schema.org',
		'@type': 'ImageObject',
		name: displayTitle(photo, annotations),
		description: photo.description || undefined,
		keywords: keywords.length ? keywords : undefined,
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
		copyrightNotice: buildCopyrightNotice(photo),
		license: license ? licensePage : undefined,
		acquireLicensePage: license ? (isArr ? contactPage : licensePage) : undefined,
		contentLocation: place
	};
}

export function displayTitle(
	photo: {
		title?: string | null;
		description?: string | null;
		original_filename: string | null;
	},
	annotations: PhotoAnnotation[] = []
): string {
	// A user-written landmark label beats the raw camera filename (036A8750.webp,
	// EOS dumps, emoji blobs) as the public title/h1/og:title. Annotations are the
	// image's real caption when title + description are both empty, so prefer them
	// before falling through to the filename. Grid callers pass no annotations and
	// keep the old title/description/filename behaviour.
	return (
		photo.title ||
		photo.description ||
		firstAnnotationText(annotations) ||
		photo.original_filename ||
		'Photo'
	);
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

// A meaningful annotation segment is a text segment (not a URL) that isn't a
// placeholder ('?', 'oops') the annotators use for "don't know yet".
function meaningfulAnnotationText(value: string): string | null {
	const trimmed = value.trim();
	const placeholder = trimmed.toLowerCase();
	if (!trimmed || placeholder === '?' || placeholder === 'oops') return null;
	return trimmed;
}

/**
 * First meaningful text segment across a photo's annotations, or '' if none.
 * Skips link segments and placeholder bodies. Used as a title fallback for
 * photos whose only human text is a landmark label (see displayTitle).
 */
export function firstAnnotationText(annotations: PhotoAnnotation[]): string {
	for (const a of annotations) {
		if (!a.body) continue;
		for (const seg of parseAnnotationBody(a.body)) {
			if (seg.kind !== 'text') continue;
			const text = meaningfulAnnotationText(seg.value);
			if (text) return text;
		}
	}
	return '';
}

/**
 * Distinct landmark labels a photo's annotations name, for schema.org keywords:
 * text segments only (URLs dropped), placeholders skipped, de-duplicated
 * case-insensitively (the raw set has repeats, e.g. 'Průmyslový palác' ×3).
 */
export function annotationKeywords(annotations: PhotoAnnotation[] = []): string[] {
	const out: string[] = [];
	for (const a of annotations) {
		if (!a.body) continue;
		for (const seg of parseAnnotationBody(a.body)) {
			if (seg.kind !== 'text') continue;
			const text = meaningfulAnnotationText(seg.value);
			if (text) out.push(text);
		}
	}
	return dedupeCaseInsensitive(out);
}

/** De-duplicate strings case-insensitively (by trimmed lowercase), keeping the
 *  first occurrence's original casing and order. Drops empties. */
export function dedupeCaseInsensitive(values: string[]): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const v of values) {
		const key = v.trim().toLowerCase();
		if (!key || seen.has(key)) continue;
		seen.add(key);
		out.push(v);
	}
	return out;
}

/** `<title>` / og:title for a photo: its display title suffixed with the site name. */
export function buildHeadTitle(photo: PublicPhoto, annotations: PhotoAnnotation[] = []): string {
	return `${displayTitle(photo, annotations)} - Hillview`;
}

/**
 * og:description / <meta name="description"> for a photo. Picks the best single
 * human-readable line available: the author's description, else the
 * reverse-geocoded place name, else the bare coordinates as a last resort.
 *
 * Deliberately does NOT splice in an annotation — cherry-picking the *first*
 * label ("… — Strojimport") was arbitrary noise; the full landmark set now lives
 * in the ImageObject's keywords, and a lone label (when it's all a photo has)
 * surfaces as the title instead (see displayTitle). Precise structured metadata
 * lives in buildPhotoImageJsonLd. Shared by the /photo/[uid] detail route and
 * the map homepage's ?photo= share cards so both emit identical head tags.
 */
export function buildHeadDescription(photo: PublicPhoto): string {
	if (photo.description) return photo.description;
	if (photo.place_name) return photo.place_name;
	if (photo.latitude != null && photo.longitude != null) {
		return `${photo.latitude.toFixed(4)}, ${photo.longitude.toFixed(4)}`;
	}
	return 'Photo on Hillview';
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
