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
	width?: number;
	height?: number;
}

export async function fetchDetections(photoId: string): Promise<PhotoDetections> {
	const res = await http.get(`/photos/${photoId}/detections`);
	if (!res.ok) throw new Error(`Failed to fetch detections: ${res.status}`);
	return res.json();
}
