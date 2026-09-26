import { http } from '$lib/http';

/**
 * Curated camera/lens EXIF for a photo, as served by the public photo endpoint
 * (`GET /api/photos/public/{uid}` → `exif`). All fields are optional; the backend
 * omits tags that aren't present. Only hillview-sourced photos carry EXIF here —
 * external sources (Mapillary, Panoramax) return no `exif`.
 */
/** [min, max] of a value that varies across a fused bracket's source frames. */
export type ExifRange = [number, number];

export interface PhotoExif {
	focal_length?: number;        // mm
	focal_length_35mm?: number;   // mm, 35mm-equivalent — the CAMERA's own tag
	// mm, 35mm-equivalent COMPUTED by exiftool (focal length x its guess at the
	// crop factor), which is not in the file at all. Served as its own field
	// since 2026-09-26: it used to be collapsed into the one above with an
	// `or`, so a reader could not tell a manufacturer's statement from a
	// derivation, and where both existed the disagreement was lost.
	focal_length_35mm_computed?: number;
	f_number?: number;            // aperture, e.g. 2.8
	iso?: number;
	exposure_time?: number;       // seconds, e.g. 0.004
	// Pipeline uploads (EXR panos, fused stacks) carry their source frames' EXIF
	// rather than one embedded exposure. A value that varies within the bracket
	// arrives as a range INSTEAD of the scalar; `_mixed` means a pano's positions
	// didn't all agree (what's sent is the predominant one).
	f_number_range?: ExifRange;
	iso_range?: ExifRange;
	exposure_time_range?: ExifRange;
	f_number_mixed?: boolean;
	iso_mixed?: boolean;
	exposure_time_mixed?: boolean;
	frames?: number;              // total source frames behind a fused pano/stack
	positions?: number;           // pano positions (stacks), when more than one
	exposure_compensation?: number; // EV
	make?: string;
	model?: string;
	lens?: string;
}

/**
 * The slice of the public photo record the info window needs: curated EXIF plus
 * the photo's real pixel dimensions. `sizes.full` on the local photo object is a
 * rendition (panos are downsized there), so true dimensions come from here.
 */
export interface PublicPhotoInfo {
	exif: PhotoExif | null;
	width?: number;
	height?: number;
}

// uid -> public info (or null on a hard 4xx/5xx). Persists for the session so
// re-focusing a photo is instant. Transient network failures are NOT cached, so
// a later attempt can retry.
const cache = new Map<string, PublicPhotoInfo | null>();
const inflight = new Map<string, Promise<PublicPhotoInfo | null>>();

/** Synchronous peek at the cache; `undefined` means "not fetched yet". */
export function getCachedPublicInfo(uid: string): PublicPhotoInfo | null | undefined {
	return cache.get(uid);
}

/**
 * Fetch (once, then cached) the public info for a photo by composite uid.
 * Returns null for non-hillview sources or a hard 4xx/5xx; a photo without
 * camera EXIF still resolves, with `exif: null`.
 */
export async function fetchPublicInfo(uid: string): Promise<PublicPhotoInfo | null> {
	const cached = cache.get(uid);
	if (cached !== undefined) return cached;

	const existing = inflight.get(uid);
	if (existing) return existing;

	const p = (async () => {
		try {
			const res = await http.get(`/photos/public/${encodeURIComponent(uid)}`);
			if (!res.ok) {
				cache.set(uid, null);
				return null;
			}
			const body = await res.json();
			const info: PublicPhotoInfo = {
				exif: (body?.exif ?? null) as PhotoExif | null,
				width: typeof body?.width === 'number' && body.width > 0 ? body.width : undefined,
				height: typeof body?.height === 'number' && body.height > 0 ? body.height : undefined
			};
			cache.set(uid, info);
			return info;
		} catch {
			// Leave uncached so a subsequent open can retry after connectivity returns.
			return null;
		} finally {
			inflight.delete(uid);
		}
	})();
	inflight.set(uid, p);
	return p;
}

// --- Display formatting -----------------------------------------------------
// Values are shown as-is (no lossy rounding). The only computed value is the
// shutter denominator, where the reciprocal of a float (e.g. 0.004 → 249.9999…)
// is snapped to the nearest integer to render the conventional "1/250 s".
// A bracket's range renders as "lo–hi" with the unit once ("1/2000–1/125 s");
// " + other" marks a pano whose positions didn't all agree.

const RANGE_DASH = '–';
const MIXED_SUFFIX = ' + other';

function withMixed(s: string, mixed?: boolean): string {
	return mixed ? s + MIXED_SUFFIX : s;
}

/**
 * `24 mm (36 mm eq.)` — and `5.58 mm (~26 mm eq.)` when the equivalent was
 * COMPUTED rather than stated by the camera.
 *
 * Both values are shown, never silently swapped for each other. Phones write 0
 * in the camera's own tag (every Ulefone Armor 22 upload does) and carry the
 * real equivalent only in exiftool's composite, so a display that used the
 * camera tag alone would lose the equivalent on most of this corpus — which is
 * what the old server-side `or` was compensating for, at the cost of hiding
 * which value you were looking at. The `~` is that distinction, made visible.
 *
 * When the camera stated one AND exiftool computed a different one, the
 * camera's is shown and both are in the `title` (see focalLengthTitle): a
 * compact line should not carry two numbers for one property, but neither
 * should it discard the one it did not pick.
 */
export function formatFocalLength(exif: PhotoExif): string | null {
	if (exif.focal_length == null) return null;
	const base = `${exif.focal_length} mm`;
	// The camera's own statement wins the line when it has one.
	if (exif.focal_length_35mm != null && exif.focal_length_35mm !== exif.focal_length) {
		return `${base} (${exif.focal_length_35mm} mm eq.)`;
	}
	// Derived, and marked as derived.
	if (exif.focal_length_35mm_computed != null &&
		exif.focal_length_35mm_computed !== exif.focal_length) {
		return `${base} (~${round1(exif.focal_length_35mm_computed)} mm eq.)`;
	}
	return base;
}

/** One decimal at most — exiftool's composite carries float noise (68.4587…). */
function round1(v: number): number {
	return Math.round(v * 10) / 10;
}

/**
 * The full story behind [formatFocalLength]'s one line, for a `title`: every
 * value the server had, each said to be what it is. Null when the line already
 * tells the whole truth.
 */
export function focalLengthTitle(exif: PhotoExif): string | null {
	const stated = exif.focal_length_35mm;
	const computed = exif.focal_length_35mm_computed;
	if (stated == null && computed == null) return null;
	const parts: string[] = [];
	if (stated != null) parts.push(`${stated} mm eq. reported by the camera`);
	if (computed != null) {
		parts.push(`${round1(computed)} mm eq. computed from the sensor size`);
	}
	// Nothing to add when there is only one value and the line already shows it.
	if (parts.length < 2) return null;
	return parts.join('; ');
}

export function formatAperture(f?: number, range?: ExifRange, mixed?: boolean): string | null {
	if (range) return withMixed(`ƒ/${range[0]}${RANGE_DASH}${range[1]}`, mixed);
	if (f == null) return null;
	return withMixed(`ƒ/${f}`, mixed);
}

export function formatIso(iso?: number, range?: ExifRange, mixed?: boolean): string | null {
	if (range) return withMixed(`ISO ${range[0]}${RANGE_DASH}${range[1]}`, mixed);
	if (iso == null) return null;
	return withMixed(`ISO ${iso}`, mixed);
}

// exiftool's own rule: below a quarter second the conventional fraction,
// otherwise the decimal ("0.4 s", "2.5 s") — "1/3 s" for 0.4 would be lossy.
function shutterCore(sec: number): string {
	if (sec < 0.25001) return `1/${Math.round(1 / sec)}`;
	return `${sec}`;
}

export function formatShutter(sec?: number, range?: ExifRange, mixed?: boolean): string | null {
	if (range && range[0] > 0 && range[1] > 0) {
		return withMixed(`${shutterCore(range[0])}${RANGE_DASH}${shutterCore(range[1])} s`, mixed);
	}
	if (sec == null || sec <= 0) return null;
	return withMixed(`${shutterCore(sec)} s`, mixed);
}

/**
 * Source-frame context: "3" for a fused single, "94" for a pano shot as singles
 * (one frame per position — nothing more to say), "36 (12 positions)" when the
 * positions hold brackets; null for a single frame.
 */
export function formatFrames(frames?: number, positions?: number): string | null {
	if (frames == null || frames < 2) return null;
	if (positions != null && positions > 1 && frames > positions) return `${frames} (${positions} positions)`;
	return `${frames}`;
}

export function formatCamera(make?: string, model?: string): string | null {
	if (!make && !model) return null;
	if (make && model) {
		// Model often already includes the make ("Canon EOS R6"); avoid "Canon Canon EOS R6".
		if (model.toLowerCase().startsWith(make.toLowerCase())) return model;
		return `${make} ${model}`;
	}
	return model || make || null;
}
