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
	/** true when ele was estimated by sampling the DEM (no OSM ele tag) */
	ele_estimated?: boolean;
	/** OSM topographic prominence in metres — sparse (~2% of peaks) but
	 * tagged precisely on the famous ones; drives label priority */
	prominence?: number | null;
	/** peak | tower (observation) | mast (communication) | city | town |
	 * village | suburb | quarter; default peak */
	kind?: string;
	/** OSM population — near-universal on place nodes (~98% around Prague);
	 * drives label priority for settlements the way prominence does peaks */
	population?: number | null;
}

/** A peak projected into the panorama: texture coords + display facts. */
export interface PeakMark {
	name: string;
	u: number;
	v: number;
	distance_m: number;
	azimuth_deg: number;
	ele?: number | null;
	prominence?: number | null;
	kind?: string;
	population?: number | null;
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

/** Default relative depth tolerance for the visibility match. The march's
 * far steps are rel_step·d (~0.5%), OSM summit coords wobble a few grid
 * cells, and depth is quantized — 6% plus a couple of quanta absorbs all
 * three. Callers may pass their own (the pane exposes it as a slider:
 * looser → more labels, at the cost of occasionally labeling a peak whose
 * summit is actually just hidden behind a similar-depth ridge).
 *
 * This value also BOUNDS THE OCCLUSION TEST, which is not obvious: the
 * "peak is hidden" stop below triggers on `d < distanceM - tol`, so
 * widening the tolerance widens the window in which occluded terrain still
 * counts as a match. Measured on a 93.8°/106 km render (667 labels): at
 * 0.06 no occluded peak got through, while at the pane slider's 0.25
 * maximum 75 % of labels pinned to the first terrain row without the test
 * ever running and 269 anchored to terrain more than 5 % off their own
 * distance — worst case a valley town labelled on a skyline 10 km behind
 * it. Past roughly 0.1 this stops being a sensitivity knob and becomes a
 * different question ("this place is in that direction" rather than "this
 * summit is what you see"), which deserves its own mode.
 * See docs/terrain-overlay-graduation.md § The label pool. */
export const PEAK_DEPTH_REL_TOL = 0.06;
export const PEAK_MIN_DISTANCE_M = 500;

/** Settlement kinds (OSM place=*) among label candidates. */
export const PLACE_KINDS = new Set(['city', 'town', 'village', 'suburb', 'quarter']);

/** Per-kind distance caps for settlements — a village at 70 km is an
 * unresolvable speck; physical vista boards cap the same way. Cities are
 * uncapped (a capital's skyline reads at any distance the render covers). */
export const PLACE_MAX_DIST_M: Record<string, number> = {
	town: 80_000,
	village: 30_000,
	suburb: 20_000,
	quarter: 15_000
};

/** Unified label priority: prominence for terrain features, population
 * (log-mapped into prominence-like metres) for settlements — 1k ≈ 180,
 * 100k ≈ 360, 1M ≈ 450, so a capital ranks with a major peak and a
 * nondescript village with a nondescript ridge. */
export function labelPriority(p: {
	prominence?: number | null;
	kind?: string;
	population?: number | null;
}): number {
	if (p.kind && PLACE_KINDS.has(p.kind)) {
		const pop = p.population ?? 0;
		return pop > 0 ? Math.max(0, 90 * Math.log10(pop / 10)) : 0;
	}
	return p.prominence ?? 0;
}

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
	peak: Peak,
	relTol = PEAK_DEPTH_REL_TOL
): PeakMark | null {
	const { bearingDeg, distanceM } = bearingDistance(meta.lat, meta.lon, peak.lat, peak.lon);
	if (distanceM < PEAK_MIN_DISTANCE_M) return null;
	if (typeof meta.max_distance_m === 'number' && distanceM > meta.max_distance_m) return null;
	const kindCap = peak.kind ? PLACE_MAX_DIST_M[peak.kind] : undefined;
	if (kindCap !== undefined && distanceM > kindCap) return null;
	const col = colForAzimuth(meta, bearingDeg);
	if (col === null) return null;
	const tol = distanceM * relTol + 2 * meta.depth_scale_m;
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
				ele: peak.ele,
				prominence: peak.prominence,
				kind: peak.kind,
				population: peak.population
			};
		}
		// nearer than the peak (beyond tolerance): monotonicity says the
		// rest of the column only gets nearer — the peak is occluded
		if (d < distanceM - tol) return null;
	}
	return null;
}

export function projectPeaks(
	meta: TerrainMeta,
	depth: Uint16Array,
	peaks: Peak[],
	relTol = PEAK_DEPTH_REL_TOL
): PeakMark[] {
	const out: PeakMark[] = [];
	for (const p of peaks) {
		const m = projectPeak(meta, depth, p, relTol);
		if (m) out.push(m);
	}
	// highest label priority first (prominence for terrain — OSM tags it
	// precisely on the famous ones, Říp beats a taller nondescript ridge;
	// population for settlements), then nearest first so downstream label
	// caps keep the most legible of the rest
	return out.sort(
		(a, b) => labelPriority(b) - labelPriority(a) || a.distance_m - b.distance_m
	);
}

/** Sky-anchored label layout (vista-board style): each pill floats directly
 * above its summit with a short leader, so the label never covers what it
 * labels — the sky above a skyline point is empty by definition.
 *
 * Input order = priority (feed prominence-first). Selection is PER SCREEN
 * NEIGHBORHOOD: a label whose target sits within minGapX of an already
 * accepted one is skipped — the best name wins its column, instead of a
 * global cap letting far famous peaks displace everything near (measured:
 * that made the tolerance slider FEEL inverted). Residual overlaps stack
 * upward; pills pushed past the top edge are dropped. Pure and
 * painter-agnostic: returns pill rects + target points; the zoomview
 * painter's edge:'bottom' case draws exactly this geometry. */
export interface SkyLabel {
	label: string;
	cx: number;
	cy: number; // target point (summit) in canvas px
	pillW: number;
	pillH: number;
	tx: number;
	ty: number; // pill top-left
	id?: string;
}

export function layoutSkyLabels(
	inputs: { label: string; cx: number; cy: number; pillW: number; id?: string }[],
	W: number,
	H: number,
	opts: { pillH?: number; gap?: number; leader?: number; minGapX?: number } = {}
): SkyLabel[] {
	const pillH = opts.pillH ?? 20;
	const gap = opts.gap ?? 3;
	const leader = opts.leader ?? 12;
	const minGapX = opts.minGapX ?? 40;
	const placed: SkyLabel[] = [];
	for (const i of inputs) {
		if (i.cx < 0 || i.cx > W || i.cy < 0 || i.cy > H) continue;
		if (placed.some((p) => Math.abs(p.cx - i.cx) < minGapX)) continue;
		const c: SkyLabel = {
			...i,
			pillH,
			tx: Math.min(Math.max(i.cx - i.pillW / 2, 2), Math.max(2, W - i.pillW - 2)),
			ty: i.cy - leader - pillH
		};
		let moved = true;
		while (moved) {
			moved = false;
			for (const p of placed) {
				const overlapX = c.tx < p.tx + p.pillW + gap && p.tx < c.tx + c.pillW + gap;
				const overlapY = c.ty < p.ty + p.pillH + gap && p.ty < c.ty + c.pillH + gap;
				if (overlapX && overlapY) {
					c.ty = p.ty - pillH - gap; // stack upward, keep tether column
					moved = true;
				}
			}
		}
		if (c.ty >= 2) placed.push(c);
	}
	return placed;
}

/** Hit test a tap against placed sky labels (slop widens the target for
 * touch). First match wins — placed order is priority order. */
export function hitSkyLabel<T extends SkyLabel>(
	placed: T[],
	x: number,
	y: number,
	slop = 4
): T | null {
	for (const l of placed) {
		if (x >= l.tx - slop && x <= l.tx + l.pillW + slop
			&& y >= l.ty - slop && y <= l.ty + l.pillH + slop)
			return l;
	}
	return null;
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
