/**
 * Anonymization detection API helpers.
 *
 * Fetches the object detections (detected_objects) stored by the worker's
 * anonymization pass, for debug visualization in the zoom view.
 */
import { http } from '$lib/http';

export interface DetectedObjectBBox {
	x1: number;
	y1: number;
	x2: number;
	y2: number;
}

export interface DetectedObject {
	class_id: number | null;
	class_name?: string;
	/** YOLO confidence 0-1; absent on manual rectangles and pre-existing photos */
	confidence?: number;
	/** Pyramid scale the detection came from (1.0 = full resolution); absent on older photos */
	scale?: number;
	/** Whether this box was actually painted over. Absent on photos processed
	 *  before the flag existed, where the server re-derives it from confidence. */
	blurred?: boolean;
	blur?: number;
	bbox: DetectedObjectBBox;
}

export interface PhotoDetections {
	photo_id: string;
	detected_objects: {
		objects: DetectedObject[];
		model_name?: string;
		manual?: boolean;
	} | null;
	/** Which set of boxes came back: 'all' for the owner and moderators,
	 *  'blurred' for everyone else — the server withholds the recorded-but-
	 *  unblurred boxes rather than advertising people it left visible. So a
	 *  short list is not necessarily a detector that found nothing. */
	scope?: 'all' | 'blurred';
	width?: number;
	height?: number;
}

export async function fetchDetections(photoId: string): Promise<PhotoDetections> {
	const res = await http.get(`/photos/${photoId}/detections`);
	if (!res.ok) throw new Error(`Failed to fetch detections: ${res.status}`);
	return res.json();
}
