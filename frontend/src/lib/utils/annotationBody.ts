/**
 * Utility for parsing annotation body text into structured items.
 *
 * Body format: pipe-separated segments, e.g. "foo | https://x.com | bar"
 * Each segment is trimmed and classified as a URL, a coordinate pair, or
 * plain text. Coordinate classification mirrors _segment_role in the Python
 * parser (enrich/api/app/parser.py); the formats live in ./coordParser.
 */

import { firstCoords, isCoordsOnly } from './coordParser';

export type BodyItem =
	| { type: 'text'; value: string }
	| { type: 'url'; value: string; display: string }
	| { type: 'coords'; value: string; lat: number; lon: number };

const URL_RE = /^https?:\/\//i;

/**
 * Extract a short display string from a URL (hostname, or hostname + path hint).
 */
function displayForUrl(url: string): string {
	try {
		const u = new URL(url);
		// Use hostname; strip leading "www."
		let host = u.hostname.replace(/^www\./, '');
		// If there's a meaningful path, append a hint
		const path = u.pathname.replace(/\/+$/, '');
		if (path && path !== '/') {
			const segments = path.split('/').filter(Boolean);
			if (segments.length > 0) {
				const last = segments[segments.length - 1];
				// Keep it short — only append if the segment is short enough
				if (last.length <= 30) {
					host += '/\u2026/' + last;
				} else {
					host += '/\u2026';
				}
			}
		}
		return host;
	} catch {
		return url;
	}
}

/**
 * Parse annotation body text into an array of structured items.
 *
 * - Splits on '|'
 * - Trims each segment
 * - Segments starting with http:// or https:// become URL items
 * - Segments containing a coordinate pair become coords items — except the
 *   first segment, which is the name slot and only counts as coords when it
 *   is nothing but a pair (parser.py _segment_role; embedded coords after a
 *   name stay part of the name)
 * - Everything else becomes plain text
 * - Empty segments are skipped
 */
export function parseAnnotationBody(body: string): BodyItem[] {
	if (!body) return [];

	const items: BodyItem[] = [];
	const segments = body.split('|');
	for (let i = 0; i < segments.length; i++) {
		const value = segments[i].trim();
		if (!value) continue;

		if (URL_RE.test(value)) {
			items.push({ type: 'url', value, display: displayForUrl(value) });
			continue;
		}
		const c = i === 0 ? (isCoordsOnly(value) ? firstCoords(value) : null) : firstCoords(value);
		if (c) {
			items.push({ type: 'coords', value, lat: c.lat, lon: c.lon });
		} else {
			items.push({ type: 'text', value });
		}
	}
	return items;
}
