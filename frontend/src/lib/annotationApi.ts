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
