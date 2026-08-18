/**
 * Graduated terrain overlay: the fitted horizon line + peak labels a curator
 * aligned in the enrichment workbench, drawn over the photo in the zoom view.
 *
 * Two fetches with very different weights, and they are deliberately separate:
 *
 *   * the DOCUMENT (a few KB) carries the fit, the baked skyline and the
 *     labels — enough to draw everything, immediately;
 *   * the DEPTH BUFFER (a few hundred KB compressed, megabytes decoded) is
 *     only needed to answer "what am I looking at?" for an arbitrary pixel,
 *     so it is fetched on the first click and cached, never up front.
 *
 * See docs/terrain-overlay-graduation.md.
 */
import { http } from '$lib/http';
import type { TerrainOverlay } from '$terrain/overlayFit';

export interface PhotoTerrainOverlay {
	photo_id: string;
	terrain_overlay: TerrainOverlay | null;
	width?: number;
	height?: number;
}

export async function fetchTerrainOverlay(photoId: string): Promise<PhotoTerrainOverlay> {
	const res = await http.get(`/photos/${photoId}/terrain-overlay`);
	if (!res.ok) throw new Error(`Failed to fetch terrain overlay: ${res.status}`);
	return res.json();
}

// One decoded depth buffer at a time: they are megabytes, and the zoom view
// only ever asks about the photo it is showing. Keyed by URL (content-
// addressed), so revisiting a photo — or another photo sharing the same
// render — reuses it.
let cachedUrl: string | null = null;
let cachedDepth: Uint16Array | null = null;
let inflight: { url: string; p: Promise<Uint16Array> } | null = null;
// bumped by every release; a fetch that resolves after one must not
// resurrect the megabytes the release just dropped
let generation = 0;

/**
 * Fetch and decode an overlay's depth buffer.
 *
 * The stored file is raw little-endian uint16 that was gzipped at rest; the
 * browser transparently un-gzips it (the pool serves Content-Encoding: gzip),
 * so what arrives is the raw buffer. Concurrent callers share one request —
 * a double-click must not start two multi-megabyte downloads.
 *
 * `expected` is the sample count the overlay's grid describes. A buffer that
 * doesn't match it is REJECTED rather than used: reading past the end of a
 * short buffer yields `undefined`, which passes the `!== 0` sky test and
 * produces a confident marker reading "NaN, NaN · NaN km". A wrong answer
 * presented as a real one is worse than an error.
 */
export async function loadOverlayDepth(url: string, expected?: number): Promise<Uint16Array> {
	if (cachedUrl === url && cachedDepth) return cachedDepth;
	if (inflight && inflight.url === url) return inflight.p;
	const gen = generation;
	const p = (async () => {
		const res = await fetch(url);
		if (!res.ok) throw new Error(`Failed to fetch terrain depth: ${res.status}`);
		const buf = await res.arrayBuffer();
		const depth = new Uint16Array(buf);
		if (expected !== undefined && depth.length !== expected) {
			throw new Error(
				`terrain depth is ${depth.length} samples, the overlay describes ${expected}` +
					' (truncated download, or served without Content-Encoding: gzip)'
			);
		}
		if (gen === generation) {
			cachedUrl = url;
			cachedDepth = depth;
		}
		return depth;
	})();
	inflight = { url, p };
	try {
		return await p;
	} finally {
		if (inflight?.url === url) inflight = null;
	}
}

/** Drop the cached buffer (leaving a photo, or on memory pressure). */
export function releaseOverlayDepth(): void {
	generation++;
	cachedUrl = null;
	cachedDepth = null;
}

/** Whether a depth buffer for this URL is already decoded and free to use. */
export function overlayDepthReady(url: string | undefined): boolean {
	return !!url && cachedUrl === url && !!cachedDepth;
}
