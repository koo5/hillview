import { http } from '$lib/http';

/**
 * Curated camera/lens EXIF for a photo, as served by the public photo endpoint
 * (`GET /api/photos/public/{uid}` → `exif`). All fields are optional; the backend
 * omits tags that aren't present. Only hillview-sourced photos carry EXIF here —
 * external sources (Mapillary, Panoramax) return no `exif`.
 */
export interface PhotoExif {
	focal_length?: number;        // mm
	focal_length_35mm?: number;   // mm, 35mm-equivalent
	f_number?: number;            // aperture, e.g. 2.8
	iso?: number;
	exposure_time?: number;       // seconds, e.g. 0.004
	exposure_compensation?: number; // EV
	make?: string;
	model?: string;
	lens?: string;
}

// uid -> curated EXIF (or null when the photo has no usable EXIF). Persists for the
// session so re-focusing a photo is instant. Transient network failures are NOT
// cached, so a later attempt can retry.
const cache = new Map<string, PhotoExif | null>();
const inflight = new Map<string, Promise<PhotoExif | null>>();

/** Synchronous peek at the cache; `undefined` means "not fetched yet". */
export function getCachedExif(uid: string): PhotoExif | null | undefined {
	return cache.get(uid);
}

/**
 * Fetch (once, then cached) the curated EXIF for a photo by composite uid.
 * Returns null for photos with no EXIF, non-hillview sources, or a hard 4xx/5xx.
 */
export async function fetchExif(uid: string): Promise<PhotoExif | null> {
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
			const exif = (body?.exif ?? null) as PhotoExif | null;
			cache.set(uid, exif);
			return exif;
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

export function formatFocalLength(exif: PhotoExif): string | null {
	if (exif.focal_length == null) return null;
	const base = `${exif.focal_length} mm`;
	// Include the 35mm-equivalent when it meaningfully differs (crop sensors).
	if (exif.focal_length_35mm != null && exif.focal_length_35mm !== exif.focal_length) {
		return `${base} (${exif.focal_length_35mm} mm eq.)`;
	}
	return base;
}

export function formatAperture(f?: number): string | null {
	if (f == null) return null;
	return `ƒ/${f}`;
}

export function formatIso(iso?: number): string | null {
	if (iso == null) return null;
	return `ISO ${iso}`;
}

export function formatShutter(sec?: number): string | null {
	if (sec == null || sec <= 0) return null;
	if (sec >= 1) return `${sec} s`;
	return `1/${Math.round(1 / sec)} s`;
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
