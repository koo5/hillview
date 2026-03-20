/**
 * Annotation API helpers.
 *
 * The server-side data model is intentionally simple (free-for-all) for the initial
 * implementation.  Future evolution should move toward a web-of-trust / RDF-based
 * schema where:
 *  - trust/karma scores determine annotation visibility
 *  - conflict resolution is handled by the trust graph rather than central moderation
 *  - annotations link to each other via superseded_by for transparent edit history
 *  - the full RDF graph can be exported / federated across instances
 *  - per-annotation endorsements / disputes form the basis of decentralised moderation
 */
import { http } from '$lib/http';

export interface AnnotationData {
	id: string;
	photo_id: string;
	user_id: string;
	body: string | null;
	target: Record<string, unknown> | null;
	is_current: boolean;
	superseded_by: string | null;
	created_at: string | null;
	event_type: string; // 'created' | 'updated' | 'deleted'
	owner_username: string | null;
}

export interface AnnotationCreate {
	body?: string | null;
	target?: Record<string, unknown> | null;
}

export async function fetchAnnotations(photoId: string): Promise<AnnotationData[]> {
	const res = await http.get(`/annotations/photos/${photoId}`);
	if (!res.ok) throw new Error(`Failed to fetch annotations: ${res.status}`);
	return res.json();
}

export async function createAnnotation(photoId: string, data: AnnotationCreate): Promise<AnnotationData> {
	const res = await http.post(`/annotations/photos/${photoId}`, data);
	if (!res.ok) throw new Error(`Failed to create annotation: ${res.status}`);
	return res.json();
}

export async function updateAnnotation(annotationId: string, data: AnnotationCreate): Promise<AnnotationData> {
	const res = await http.put(`/annotations/${annotationId}`, data);
	if (!res.ok) throw new Error(`Failed to update annotation: ${res.status}`);
	return res.json();
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
	const res = await http.delete(`/annotations/${annotationId}`);
	if (!res.ok) throw new Error(`Failed to delete annotation: ${res.status}`);
}

/**
 * Convert annotation target from [0,1] normalized space to pixel space.
 * Used when loading DB annotations into Annotorious (which works in pixels).
 */
export function targetToPixels(
	target: Record<string, unknown> | null,
	imgWidth: number,
	imgHeight: number,
): Record<string, unknown> | null {
	return _transformTarget(target, imgWidth, imgHeight, false);
}

/**
 * Convert annotation target from pixel space to [0,1] normalized space.
 * Used when saving Annotorious annotations to the DB.
 */
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
