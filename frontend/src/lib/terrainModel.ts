/**
 * Terrain mode — pure model (docs/terrain-mode.md).
 *
 * Deliberately store-free and side-effect-free so vitest covers it without
 * dragging in leaflet/tauri: marker-state mapping and the range circle's
 * spatial selection live here; the stores/polling wrap it in
 * terrain.svelte.ts.
 */
import { destinationPoint, distanceBetween } from '$lib/geo';
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

/** Above (just below, really) this FOV the whole panorama is in view and a
 * wedge would be a meaningless full disc — draw nothing instead. */
export const WEDGE_MAX_FOV_DEG = 355;

/** The map's view wedge as a leaflet-ready sector polygon: viewpoint +
 * sampled arc at radiusM, spanning azimuthDeg ± fovDeg/2. Purely DERIVED
 * geometry (pane → map, one-way — wedge-dragging as an input is deferred
 * sugar, maybe never). Returns null when the full panorama is visible. */
export function wedgeArcLatLngs(
	viewpoint: { lat: number; lon: number },
	azimuthDeg: number,
	fovDeg: number,
	radiusM: number,
	samples = 24
): [number, number][] | null {
	if (fovDeg >= WEDGE_MAX_FOV_DEG) return null;
	const fov = Math.max(2, fovDeg); // keep a sliver visible when zoomed deep
	const pts: [number, number][] = [[viewpoint.lat, viewpoint.lon]];
	for (let i = 0; i <= samples; i++) {
		const az = azimuthDeg - fov / 2 + (fov * i) / samples;
		const q = destinationPoint(viewpoint.lat, viewpoint.lon, az, radiusM / 1000);
		pts.push([q.lat, q.lng]);
	}
	return pts;
}
