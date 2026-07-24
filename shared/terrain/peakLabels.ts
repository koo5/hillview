/**
 * Peak labels for the terrain depth-pano viewer (terrain-mode v2, per
 * docs/terrain-mode.md: OSM natural=peak labels drawn via the existing
 * zoomview label layouter).
 *
 * This module is the terrain-specific half: pure functions that project a
 * peak (lat, lon) into panorama texture coordinates and decide VISIBILITY
 * from the depth buffer itself — a peak is labeled only if the rendered
 * surface in its direction sits at the peak's distance. A nearer ridge in
 * the same column leaves no matching depth, so occluded peaks label
 * themselves out; no line-of-sight recomputation, the render already did
 * that work. The generic half (edge pills, overlap resolution, painting) is
 * shared/zoomview/labelLayout.ts + labelPaint.ts, unchanged.
 *
 * Dependency-free like the viewer; everything here is unit-testable without
 * GL or DOM.
 */
import {
	textureAspect,
	wrap01,
	type TerrainMeta,
	type ViewRect
} from './depthPanoViewer';

const R_EARTH_M = 6371000;

export interface Peak {
	name: string;
	lat: number;
	lon: number;
	/** summit elevation in metres, when the source knows it */
	ele?: number | null;
}

/** A peak projected into the panorama: texture coords + display facts. */
export interface PeakMark {
	name: string;
	u: number;
	v: number;
	distance_m: number;
	azimuth_deg: number;
	ele?: number | null;
}

/** Inverse geodesic on the same sphere as destinationPoint (haversine
 * distance + initial bearing), so projection and click-back agree. */
export function bearingDistance(
	lat1: number,
	lon1: number,
	lat2: number,
	lon2: number
): { bearingDeg: number; distanceM: number } {
	const la1 = (lat1 * Math.PI) / 180;
	const la2 = (lat2 * Math.PI) / 180;
	const dLa = la2 - la1;
	const dLo = ((lon2 - lon1) * Math.PI) / 180;
	const a =
		Math.sin(dLa / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2;
	const distanceM = 2 * R_EARTH_M * Math.asin(Math.min(1, Math.sqrt(a)));
	const y = Math.sin(dLo) * Math.cos(la2);
	const x = Math.cos(la1) * Math.sin(la2) - Math.sin(la1) * Math.cos(la2) * Math.cos(dLo);
	const bearingDeg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
	return { bearingDeg, distanceM };
}

/** Inverse of azimuthForColumn: nearest column index for an azimuth, or
 * null when the sweep doesn't cover it (partial panoramas). */
export function colForAzimuth(meta: TerrainMeta, azimuthDeg: number): number | null {
	const step =
		meta.az_step_deg ?? (meta.width > 1 ? (meta.az_end - meta.az_start) / (meta.width - 1) : 0);
	if (!(step > 0)) return null;
	const col = Math.round((((azimuthDeg - meta.az_start) % 360) + 360) % 360 / step);
	return col >= 0 && col < meta.width ? col : null;
}

/** Relative depth tolerance for the visibility match. The march's far steps
 * are rel_step·d (~0.5%), OSM summit coords wobble a few grid cells, and
 * depth is quantized — 6% plus a couple of quanta absorbs all three. */
export const PEAK_DEPTH_REL_TOL = 0.06;
export const PEAK_MIN_DISTANCE_M = 500;

/** Project one peak into the panorama, or null when out of range, outside
 * the sweep, or occluded. The row is found by scanning the peak's column
 * for the TOPMOST pixel whose depth matches the peak's distance — the
 * rendered summit edge — which sidesteps eye/refraction bookkeeping and
 * pins the label to what's actually on screen. Column depth is monotone
 * non-increasing below the skyline (smaller pixel angle → earlier horizon
 * crossing), so the scan walks down past farther background ridges and
 * stops for good once the terrain is nearer than the peak. */
export function projectPeak(
	meta: TerrainMeta,
	depth: Uint16Array,
	peak: Peak
): PeakMark | null {
	const { bearingDeg, distanceM } = bearingDistance(meta.lat, meta.lon, peak.lat, peak.lon);
	if (distanceM < PEAK_MIN_DISTANCE_M) return null;
	if (typeof meta.max_distance_m === 'number' && distanceM > meta.max_distance_m) return null;
	const col = colForAzimuth(meta, bearingDeg);
	if (col === null) return null;
	const tol = distanceM * PEAK_DEPTH_REL_TOL + 2 * meta.depth_scale_m;
	for (let row = 0; row < meta.height; row++) {
		const q = depth[row * meta.width + col];
		if (q === 0) continue; // sky above the skyline
		const d = q * meta.depth_scale_m;
		if (Math.abs(d - distanceM) <= tol) {
			return {
				name: peak.name,
				u: (col + 0.5) / meta.width,
				v: (row + 0.5) / meta.height,
				distance_m: distanceM,
				azimuth_deg: bearingDeg,
				ele: peak.ele
			};
		}
		// nearer than the peak (beyond tolerance): monotonicity says the
		// rest of the column only gets nearer — the peak is occluded
		if (d < distanceM - tol) return null;
	}
	return null;
}

export function projectPeaks(meta: TerrainMeta, depth: Uint16Array, peaks: Peak[]): PeakMark[] {
	const out: PeakMark[] = [];
	for (const p of peaks) {
		const m = projectPeak(meta, depth, p);
		if (m) out.push(m);
	}
	// nearest first, so caps keep the most legible labels
	return out.sort((a, b) => a.distance_m - b.distance_m);
}

/** Texture coords → canvas pixels under a viewport rect, on the cylinder:
 * the horizontal delta wraps, so a seam-straddling view still places marks
 * correctly. Null when the mark is outside the viewport horizontally
 * (vertical culling is the layouter's job). */
export function texToCanvas(
	meta: TerrainMeta,
	rect: ViewRect,
	u: number,
	v: number,
	W: number,
	H: number
): { cx: number; cy: number } | null {
	const rw = rect.x2 - rect.x1;
	if (!(rw > 0)) return null;
	const dx = wrap01(u - wrap01(rect.x1));
	if (dx > rw) return null;
	const yOsd = v * textureAspect(meta);
	return { cx: (dx / rw) * W, cy: ((yOsd - rect.y1) / (rect.y2 - rect.y1)) * H };
}
