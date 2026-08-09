/**
 * Annotation target-space conversion — extracted verbatim from annotationApi.ts
 * for reuse by the enrichment workbench. Pure: no http, no DOM.
 *
 * DB targets store [0,1]-normalized coordinates (dimension-independent);
 * Annotorious works in image pixel space. Two selector encodings are handled:
 * RECTANGLE geometry objects and W3C media-fragment `xywh=pixel:` strings.
 */

export function targetToPixels(
	target: Record<string, unknown> | null,
	imgWidth: number,
	imgHeight: number,
): Record<string, unknown> | null {
	return _transformTarget(target, imgWidth, imgHeight, false);
}

export function targetToNormalized(
	target: Record<string, unknown> | null,
	imgWidth: number,
	imgHeight: number,
): Record<string, unknown> | null {
	return _transformTarget(target, imgWidth, imgHeight, true);
}

function _transformTarget(
	target: Record<string, unknown> | null,
	imgWidth: number,
	imgHeight: number,
	normalize: boolean,
): Record<string, unknown> | null {
	if (!target || !imgWidth || !imgHeight) return target;

	// Deep clone to avoid mutating the original
	const result = JSON.parse(JSON.stringify(target));
	const selectorRaw = result.selector;
	if (!selectorRaw) return result;

	const selectors = Array.isArray(selectorRaw) ? selectorRaw : [selectorRaw];

	for (const sel of selectors) {
		if (sel.type === 'RECTANGLE' && sel.geometry) {
			const g = sel.geometry;
			if (normalize) {
				g.x = g.x / imgWidth;
				g.y = g.y / imgHeight;
				g.w = g.w / imgWidth;
				g.h = g.h / imgHeight;
			} else {
				g.x = g.x * imgWidth;
				g.y = g.y * imgHeight;
				g.w = g.w * imgWidth;
				g.h = g.h * imgHeight;
			}
		} else if (typeof sel.value === 'string' && sel.value.includes('xywh=')) {
			const match = sel.value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/);
			if (match) {
				let [, x, y, w, h] = match.map(Number);
				if (normalize) {
					x /= imgWidth; y /= imgHeight; w /= imgWidth; h /= imgHeight;
				} else {
					x *= imgWidth; y *= imgHeight; w *= imgWidth; h *= imgHeight;
				}
				sel.value = `xywh=pixel:${x},${y},${w},${h}`;
			}
		}
	}

	if (!Array.isArray(selectorRaw)) {
		result.selector = selectors[0];
	}

	return result;
}

/**
 * Read the [0,1]-normalized rectangle out of a DB target, handling the same
 * two selector encodings as _transformTarget. Null when the target carries no
 * usable rect (absent target, foreign selector type, malformed value).
 */
export function targetRectNormalized(
	target: Record<string, unknown> | null | undefined,
): { x: number; y: number; w: number; h: number } | null {
	const selectorRaw = (target as { selector?: unknown } | null | undefined)?.selector;
	if (!selectorRaw) return null;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	const selectors: any[] = Array.isArray(selectorRaw) ? selectorRaw : [selectorRaw];
	for (const sel of selectors) {
		if (sel?.type === 'RECTANGLE' && sel.geometry) {
			const { x, y, w, h } = sel.geometry;
			if ([x, y, w, h].every((v: unknown) => typeof v === 'number' && isFinite(v))) {
				return { x, y, w, h };
			}
		} else if (typeof sel?.value === 'string' && sel.value.includes('xywh=')) {
			const match = sel.value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/);
			if (match) {
				const [, x, y, w, h] = match.map(Number);
				return { x, y, w, h };
			}
		}
	}
	return null;
}

/**
 * Map a normalized target rect to view bounds in OpenSeadragon viewport units
 * (x AND y both normalized by image width — the x1..y2 URL params the map
 * homepage's applyInitialBounds and /shared/ links already consume). The
 * window is the rect expanded per axis by `zoomOut` (default 1.4 = margins of
 * 20% of THAT side on each side, so the window scales with the annotation,
 * not the photo — tight on purpose, practical on mobile). No squaring: the
 * viewer's fitBounds guarantees the whole passed window ends up visible,
 * letterboxing it into the container — which also means URLs read back from
 * the address bar carry the post-fit viewport, not this window.
 * `minHeightFrac` can floor both spans at a fraction of the image HEIGHT for
 * point-sized labels; off by default — annotators draw usable boxes. The
 * floor is height-relative on purpose: a width-relative floor is aspect-blind
 * — on a 10:1 panorama, 12% of the width is taller than the whole image
 * strip, which zoomed the view out until the label was a lost dot. The
 * window is then clamped inside the image per axis (centred on an axis it
 * exceeds), so a label on the horizon doesn't open half sky outside the
 * frame. New math, not a zoomview extraction: zoomview only ever serializes
 * the live viewport (share) — nothing computed a viewport from an annotation
 * target before this.
 */
export function rectToViewBounds(
	rect: { x: number; y: number; w: number; h: number },
	imgWidth: number,
	imgHeight: number,
	zoomOut = 1.4,
	minHeightFrac = 0,
): { x1: number; y1: number; x2: number; y2: number } | null {
	if (!imgWidth || !imgHeight) return null;
	const aspect = imgHeight / imgWidth;
	const w = rect.w;
	const h = rect.h * aspect;
	const floor = minHeightFrac * aspect;
	const halfW = Math.max(w * zoomOut, floor) / 2;
	const halfH = Math.max(h * zoomOut, floor) / 2;
	// Centre on the rect, then keep the window inside the image on each axis
	// (or centre on the image when the window is larger than the image extent).
	const clampCentre = (c: number, extent: number, half: number) =>
		2 * half >= extent ? extent / 2 : Math.min(Math.max(c, half), extent - half);
	const cx = clampCentre(rect.x + w / 2, 1, halfW);
	const cy = clampCentre(rect.y * aspect + h / 2, aspect, halfH);
	return { x1: cx - halfW, y1: cy - halfH, x2: cx + halfW, y2: cy + halfH };
}

/**
 * Build a W3C Web Annotation for Annotorious from a DB annotation row —
 * extracted verbatim from OpenSeadragonViewer's syncAnnotationsToViewer.
 * The target is converted from normalized to pixel space for the given dims.
 */
export function toW3cAnnotation(
	a: { id: string; body: string | null; target: Record<string, unknown> | null },
	imgWidth: number,
	imgHeight: number,
): Record<string, unknown> {
	return {
		'@context': 'http://www.w3.org/ns/anno.jsonld',
		id: a.id,
		type: 'Annotation',
		body: a.body
			? [{ type: 'TextualBody', value: a.body, purpose: 'commenting' }]
			: [],
		target: targetToPixels(a.target, imgWidth, imgHeight),
	};
}
