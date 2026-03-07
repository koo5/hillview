/**
 * Utility for parsing annotation body text into structured items.
 *
 * Body format: pipe-separated segments, e.g. "foo | https://x.com | bar"
 * Each segment is trimmed and classified as either a URL or plain text.
 */

export type BodyItem =
	| { type: 'text'; value: string }
	| { type: 'url'; value: string; display: string };

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
 * - Everything else becomes plain text
 * - Empty segments are skipped
 */
export function parseAnnotationBody(body: string): BodyItem[] {
	if (!body) return [];

	const items: BodyItem[] = [];
	for (const raw of body.split('|')) {
		const value = raw.trim();
		if (!value) continue;

		if (URL_RE.test(value)) {
			items.push({ type: 'url', value, display: displayForUrl(value) });
		} else {
			items.push({ type: 'text', value });
		}
	}
	return items;
}
