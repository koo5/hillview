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
