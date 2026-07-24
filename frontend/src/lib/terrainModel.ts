/**
 * Terrain mode — pure model (docs/terrain-mode.md).
 *
 * Deliberately store-free and side-effect-free so vitest covers it without
 * dragging in leaflet/tauri: marker-state mapping and the range circle's
 * spatial selection live here; the stores/polling wrap it in
 * terrain.svelte.ts.
 */
import { distanceBetween } from '$lib/geo';
import type { TerrainMeta } from '$terrain/depthPanoViewer';

/** A row from GET /terrain/renders (workbench API today; graduation to the
 * main backend is an open question tracked in the design doc). */
export interface TerrainRender {
	id: string;
	photo_id: string | null;
	lat: number;
	lon: number;
	status: string; // queued | rendering (progress ship-order) | done | error
	error: string | null;
	meta: TerrainMeta | null;
	has_depth: boolean;
	has_preview: boolean;
	enqueued_at: string;
	finished_at: string | null;
}

/** Map-marker states, straight from the design doc: hollow/pulsing = queued,
 * progress ring = rendering, solid = done, red = failed. In-progress renders
 * are first-class citizens. */
export type TerrainMarkerState = 'queued' | 'rendering' | 'done' | 'failed';

export function markerStateOf(r: Pick<TerrainRender, 'status'>): TerrainMarkerState {
	switch (r.status) {
		case 'done':
			return 'done';
		case 'rendering':
			return 'rendering';
		case 'error':
		case 'failed':
			return 'failed';
		default:
			return 'queued';
	}
}

/** A render is viewable once its artifacts exist — which includes partial
 * panoramas later (v1.5 streaming): status alone doesn't gate viewing. */
export function isViewable(r: TerrainRender): boolean {
	return !!(r.meta && r.has_depth && r.has_preview);
}

/** "The range circle keeps its job — it selects a render, spatially": the
 * nearest render viewpoint within range of the map center, or null. Tapping
 * a marker navigates by moving the center there, so explicit taps and
 * spatial selection are the same mechanism. */
export function nearestRenderWithin(
	renders: readonly TerrainRender[],
	center: { lat: number; lng: number },
	rangeM: number
): TerrainRender | null {
	let best: TerrainRender | null = null;
	let bestM = rangeM;
	for (const r of renders) {
		const dM = distanceBetween(center.lat, center.lng, r.lat, r.lon) * 1000;
		if (dM <= bestM) {
			best = r;
			bestM = dM;
		}
	}
	return best;
}
