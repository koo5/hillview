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
import { parseDepthBlob } from '$terrain/depthPanoViewer';

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
/** Inflate when the bytes are a gzip stream, else pass them through.
 *
 * Unambiguous by construction: the payload underneath is an HVD1 container
 * (see overlayFit.parseDepthBlob), which starts with "HVD1" — a gzip stream
 * starts with 1f 8b 08. The third byte is checked too: 0x08 is the only
 * compression method gzip defines.
 *
 * Exported for tests. */
export async function inflateIfGzip(buf: ArrayBuffer): Promise<ArrayBuffer> {
	const head = new Uint8Array(buf, 0, Math.min(3, buf.byteLength));
	if (head.length < 3 || head[0] !== 0x1f || head[1] !== 0x8b || head[2] !== 0x08) return buf;
	if (typeof DecompressionStream === 'undefined')
		throw new Error('terrain depth arrived gzipped and this browser cannot inflate it');
	const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
	return await new Response(stream).arrayBuffer();
}

export async function loadOverlayDepth(
	url: string,
	expect?: { width: number; height: number }
): Promise<Uint16Array> {
	if (cachedUrl === url && cachedDepth) return cachedDepth;
	if (inflight && inflight.url === url) return inflight.p;
	const gen = generation;
	const p = (async () => {
		const res = await fetch(url);
		if (!res.ok) throw new Error(`Failed to fetch terrain depth: ${res.status}`);
		let buf = await res.arrayBuffer();
		// The blob is stored gzipped (…depth.bin.gz). A server that sets
		// Content-Encoding: gzip hands us the container; a plain file server
		// (Caddy's file_server, a CDN that doesn't touch .gz) hands us the gzip
		// bytes as-is — so the transport is decided by the gzip magic and the
		// payload identifies itself. Measured 2026-08-20: inflating here is
		// ~2× cheaper than Content-Encoding, because only the 126 KB crosses
		// the network-service→renderer boundary, not the 5.5 MB.
		buf = await inflateIfGzip(buf);
		const depth = parseDepthBlob(buf, expect);
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
