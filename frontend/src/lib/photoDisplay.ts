export interface PhotoSize {
	url: string;
	width: number;
	height: number;
	path?: string;
}

export interface PublicPhoto {
	id: string;
	uid: string;
	source?: string;
	original_filename: string | null;
	description: string | null;
	is_public?: boolean;
	latitude: number | null;
	longitude: number | null;
	bearing: number | null;
	altitude?: number | null;
	width: number | null;
	height: number | null;
	captured_at: string | null;
	uploaded_at: string | null;
	processing_status?: string;
	sizes: Record<string, PhotoSize> | null;
	owner_id: string | null;
	owner_username: string | null;
	user_rating: 'thumbs_up' | 'thumbs_down' | null;
	rating_counts: { thumbs_up: number; thumbs_down: number };
	is_own_photo: boolean;
}

export interface PhotoAnnotation {
	id: string;
	photo_id?: string;
	user_id?: string;
	body: string | null;
	target?: unknown;
	owner_username: string | null;
	created_at: string | null;
	is_current?: boolean;
	event_type?: string;
}

export type AnnotationBodySegment =
	| { kind: 'text'; value: string }
	| { kind: 'link'; value: string };

export const DISPLAY_SIZE_KEYS = ['1200', '1024', 'full', '640', '320'];
export const THUMB_SIZE_KEYS = ['320', '640', '1024', '1200', 'full'];
// Prefer crop variants for OG (proper 1.91:1 aspect for social cards) before falling back to
// raw sizes, which can be extreme aspect ratios for panoramas.
export const OG_SIZE_KEYS = ['1200_crop', '320_crop', '1200', '1024', 'full', '640'];

export function pickSize(
	photo: { sizes: Record<string, PhotoSize> | null },
	preferred: string[]
): PhotoSize | null {
	if (!photo.sizes) return null;
	for (const key of preferred) {
		if (photo.sizes[key]) return photo.sizes[key];
	}
	return null;
}

export function getDisplayImageUrl(photo: { sizes: Record<string, PhotoSize> | null }): string {
	return pickSize(photo, DISPLAY_SIZE_KEYS)?.url ?? '';
}

export function displayTitle(photo: {
	description: string | null;
	original_filename: string | null;
}): string {
	return photo.description || photo.original_filename || 'Photo';
}

export function parseAnnotationBody(body: string | null | undefined): AnnotationBodySegment[] {
	if (!body) return [];
	return body
		.split('|')
		.map((s) => s.trim())
		.filter((s) => s.length > 0)
		.map((s): AnnotationBodySegment =>
			/^https?:\/\//i.test(s) ? { kind: 'link', value: s } : { kind: 'text', value: s }
		);
}

export function formatDate(value: string | null | undefined): string {
	if (!value) return '';
	try {
		return new Date(value).toLocaleDateString();
	} catch {
		return value;
	}
}

export function formatDateTime(value: string | null | undefined): string {
	if (!value) return '';
	try {
		return new Date(value).toLocaleString();
	} catch {
		return value;
	}
}
