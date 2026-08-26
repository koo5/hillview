import { HILLVIEW_BASE_URL, constructUserProfileUrl } from './urlUtilsServer';
import { isCoordsOnly, splitOnCoords } from './utils/coordParser';
import { parseInstant, formatDate as isoFormatDate, formatDateTimeZoned } from './dateUtils';

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
	featured?: boolean;
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
		place_name?: string | null;
		original_filename: string | null;
	},
	annotations: PhotoAnnotation[] = []
): string {
	// A user-written landmark label beats the raw camera filename (036A8750.webp,
	// EOS dumps, emoji blobs) as the public title/h1/og:title. Annotations are the
	// image's real caption when title + description are both empty, so prefer them
	// before falling through to the filename. Grid callers pass no annotations and
	// keep the old title/description/filename behaviour.
	//
	// The reverse-geocoded place ("Sedlec, Kutná Hora") replaces the machine
	// filename, which is worse than nothing here — on /bestof and /activity it is
	// also the anchor text of the link to the photo's page, so it was telling
	// search engines that page is about "hillview_photo_1786290382280.jpg".
	// place_name is populated out-of-band by backfill_places.py (the `places`
	// compose service).
	//
	// A landmark and a place answer different questions — what is in the frame
	// vs where it was taken — so when only annotations caption the photo (half of
	// the annotated ones carry no title or description) they are joined rather
	// than ranked: "Chrám svaté Barbory — Sedlec, Kutná Hora". Author-written text
	// gets no such suffix; it is a caption already.
	const { landmark, place, fallback } = titleParts(photo, annotations);
	if (fallback !== undefined) return fallback;
	if (landmark && place) return `${landmark} — ${place}`;
	return landmark || place || 'Photo';
}

/**
 * Whether the title shown for this photo draws on the reverse-geocoded place —
 * i.e. whether displaying it obliges us to credit OpenStreetMap (ODbL). Derived
 * from the same resolution displayTitle runs, so the two cannot disagree; a
 * separate re-implementation of the precedence would answer "is a place_name
 * stored" instead of "is one on screen", and those differ for every photo that
 * has a title of its own.
 */
export function titleUsesPlace(
	photo: Parameters<typeof displayTitle>[0],
	annotations: PhotoAnnotation[] = []
): boolean {
	return !!titleParts(photo, annotations).place;
}

function titleParts(
	photo: Parameters<typeof displayTitle>[0],
	annotations: PhotoAnnotation[]
): { landmark: string; place: string; fallback?: string } {
	const none = { landmark: '', place: '' };
	if (photo.title) return { ...none, fallback: photo.title };
	if (photo.description) return { ...none, fallback: photo.description };
	const landmark = firstAnnotationText(annotations);
	const place = photo.place_name || '';
	if (!landmark && !place && photo.original_filename) {
		return { ...none, fallback: photo.original_filename };
	}
	return { landmark, place };
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
// placeholder ('?', 'oops') the annotators use for "don't know yet", and isn't a
// bare coordinate pair. Annotators routinely pin a landmark's position as its own
// segment, so without this ~half of a dense photo's segments are geo strings —
// which say nothing about *what* is in the frame and so belong in neither the
// schema.org keywords nor the title fallback (an untitled photo whose first
// segment is a pair would otherwise get "49.9561603N, 15.2874025E" as its
// og:title). Same fullmatch rule the backend parser applies to the name slot.
function meaningfulAnnotationText(value: string): string | null {
	const trimmed = value.trim();
	const placeholder = trimmed.toLowerCase();
	if (!trimmed || placeholder === '?' || placeholder === 'oops') return null;
	if (isCoordsOnly(trimmed)) return null;
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
 * One line naming what the photo's annotations identify, for photos whose
 * author wrote no description: distinct labels, most notable first, packed
 * into a character budget with a "+N" tail for the rest.
 *
 * One label per annotation (its name slot), not every text segment — the flat
 * landmark set already lives in annotationKeywords. "Most notable first" is
 * read off annotator behaviour rather than any heuristic of ours: a label
 * whose annotation carries a reference link (Wikipedia, monument register)
 * was worth sourcing to whoever pinned it, so linked labels lead and
 * unlinked ones fill the remaining budget. Near-connector-free format on
 * purpose: labels arrive in the photo's language while the UI is English,
 * and a bare comma list reads fine in both.
 */
export function buildAnnotationSummary(annotations: PhotoAnnotation[] = [], budget = 150): string {
	const linked: string[] = [];
	const unlinked: string[] = [];
	for (const a of annotations) {
		if (!a.body) continue;
		const segments = parseAnnotationBody(a.body);
		const raw = segments
			.filter((s) => s.kind === 'text')
			.map((s) => meaningfulAnnotationText(s.value))
			.find(Boolean);
		if (!raw) continue;
		// The name slot may carry an embedded position ("Kostel sv. Štěpána
		// (Malín) 49.966892, 15.305111") — display keeps it, a summary doesn't.
		const label = splitOnCoords(raw)
			.filter((r) => r.type === 'text')
			.map((r) => r.value)
			.join(' ')
			.replace(/\s+/g, ' ')
			.trim();
		if (!label) continue;
		(segments.some((s) => s.kind === 'link') ? linked : unlinked).push(label);
	}
	const labels = dedupeCaseInsensitive([...linked, ...unlinked]);
	if (!labels.length) return '';

	const taken: string[] = [];
	let length = 0;
	for (const label of labels) {
		const cost = label.length + (taken.length ? 2 : 0);
		// Always take at least one label, even an over-budget one
		if (taken.length && length + cost > budget) break;
		taken.push(label);
		length += cost;
	}
	const rest = labels.length - taken.length;
	return taken.join(', ') + (rest > 0 ? ` +${rest}` : '');
}

// Google renders roughly this many characters of a description before cutting
const SNIPPET_BUDGET = 155;

/**
 * og:description / <meta name="description"> for a photo. The author's
 * description leads — but a short one ("Pohled na Kutnou Horu, Čáslav, ...")
 * leaves most of the snippet to the crawler's improvisation (menu items,
 * whatever), so when it leaves meaningful room inside the snippet budget it
 * is topped up with the composed annotation summary (" • " separated; see
 * buildAnnotationSummary — an *aggregate*, unlike the arbitrary first-label
 * cherry-pick this function once deliberately refused). Without a
 * description: place name plus the summary; bare coordinates only as a last
 * resort. Precise structured metadata lives in buildPhotoImageJsonLd. Shared
 * by the /photo/[uid] detail route and the map homepage's ?photo= share
 * cards so both emit identical head tags.
 */
export function buildHeadDescription(
	photo: PublicPhoto,
	annotations: PhotoAnnotation[] = []
): string {
	if (photo.description) {
		const room = SNIPPET_BUDGET - photo.description.length - ' • '.length;
		const summary = room >= 30 ? buildAnnotationSummary(annotations, room) : '';
		return summary ? `${photo.description} • ${summary}` : photo.description;
	}
	const parts = [photo.place_name, buildAnnotationSummary(annotations)].filter(Boolean);
	if (parts.length) return parts.join(' — ');
	if (photo.latitude != null && photo.longitude != null) {
		return `${photo.latitude.toFixed(4)}, ${photo.longitude.toFixed(4)}`;
	}
	return 'Photo on Hillview';
}

// Backend timestamps are UTC. Most endpoints stamp the 'Z' explicitly
// (common/utc.py format_utc), but a few emit naive .isoformat() strings —
// which new Date() would read in the viewer's zone, silently shifting the
// instant by the viewer's offset. parseInstant treats an offset-less string
// as UTC.
export function parseUtcTimestamp(value: string): Date {
	return parseInstant(value) ?? new Date(NaN);
}

export const formatDate = isoFormatDate;

// The zone suffix makes the rendered zone explicit ("… 15:29:13 UTC+02:00") —
// the stored instant is UTC and the conversion target is the viewer's zone,
// so without the label the time reads as an unqualified wall-clock.
export const formatDateTime = formatDateTimeZoned;
