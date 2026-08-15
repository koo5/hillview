/**
 * Terrain overlay fit: the pano↔render alignment authored in the workbench's
 * /terrain/overlay bench, and the geometry that turns it into pixels.
 *
 * This module is the SHARED half of the overlay story (docs/terrain-overlay-
 * graduation.md). The bench fits, the main app draws, and both must agree to
 * the pixel — so the projection lives here once instead of twice:
 *
 *   fit (≈200 bytes)  +  skyline (elev angle per render column)
 *        └─ projector ─┘
 *                      └→ a polyline in IMAGE pixel space
 *
 * Everything is pure and unit-space-agnostic: the projector is built for a
 * (W, H) box and every term scales linearly with it, so the bench can pass
 * its contain-fitted CSS box and the zoom view can pass the photo's natural
 * pixel size, and both get the same curve.
 *
 * The graduated document (TerrainOverlay) carries two layers with different
 * jobs: the BAKED skyline draws the horizon instantly from a few KB, and the
 * referenced depth buffer — fetched lazily, on first click — turns every
 * pixel into coordinates. Drawing never waits for the depth; interaction
 * never needs the terrain worker.
 */
import { pickFromDepthOrHorizon, type TerrainPick } from './depthPanoViewer';
import { colForAzimuth } from './peakLabels';

/** Manual pano↔render alignment (the hv:terrainOverlayFit fact, canonical
 * JSON). Pure image-intrinsic geometry — which render it was fitted against
 * is provenance, and lives outside the fit. */
export interface OverlayFit {
	/** pano output projection from the stitch .pto p-line: f0 rectilinear,
	 * f1 cylindrical, f2 equirect. VARIES per pano — never assume. */
	projection: 'equirect' | 'cylindrical' | 'rectilinear' | string;
	/** absolute bearing of the image centre column, degrees */
	centre_bearing: number;
	/** horizontal field of view across the full width, degrees */
	fov_deg: number;
	/** horizon line position, % of image height */
	horizon_pct: number;
	/** vertical trim × the equirectangular square-pixel guess */
	v_scale: number;
	/** global roll, degrees (applied as a shear) */
	roll_deg: number;
	/** piecewise-linear vertical warp: per-handle offsets in DEGREES,
	 * left→right, index 0 = left edge. 2 handles = plain roll+offset; more
	 * absorb per-seam pano stitching wobble. */
	warp: number[];
	/** atmospheric visibility read off the photo, km; null/absent = full
	 * render range. A hard distance cutoff, not a shading term. */
	visibility_km?: number | null;
	/** client wall-clock of the change (epoch ms) — drafts/live state only;
	 * facts stay timestamp-free, being content-addressed. */
	saved_at?: number;
}

/** Signed angle difference in (-180, 180]. */
export function wrapDelta(d: number): number {
	return ((((d + 180) % 360) + 360) % 360) - 180;
}

/** Warp offset (degrees, + = up) at horizontal fraction 0..1. */
export function warpAt(warp: number[], frac: number): number {
	const n = warp.length;
	if (!n) return 0;
	if (n === 1) return warp[0];
	const pos = Math.min(1, Math.max(0, frac)) * (n - 1);
	const i0 = Math.floor(pos);
	const i1 = Math.min(n - 1, i0 + 1);
	return warp[i0] + (warp[i1] - warp[i0]) * (pos - i0);
}

/** Change control-point count, preserving the current warp shape. */
export function resampleWarp(old: number[], n: number): number[] {
	n = Math.min(9, Math.max(2, n));
	if (old.length === n) return old.slice();
	const out: number[] = [];
	for (let i = 0; i < n; i++) {
		const pos = (i / (n - 1)) * (old.length - 1);
		const i0 = Math.floor(pos);
		const i1 = Math.min(old.length - 1, i0 + 1);
		out.push(old[i0] + (old[i1] - old[i0]) * (pos - i0));
	}
	return out;
}

/** A point on the image: x across the width, y down from the top, both in
 * the projector's (W, H) units. */
export interface OverlayPoint {
	x: number;
	y: number;
}

/** A direction through the photo: where an image pixel is looking. */
export interface OverlayRay {
	/** absolute azimuth, degrees */
	azimuth_deg: number;
	/** elevation angle above the horizon, degrees */
	elev_deg: number;
}

export interface OverlayProjector {
	/** the fit's (W, H) box */
	W: number;
	H: number;
	/** vertical scale at the horizon centre, px per degree */
	pxPerDeg: number;
	/** warped + rolled horizon line: y at image x */
	horizonY(x: number): number;
	/** (azimuth delta from centre, elevation angle)° → image point, or null
	 * when the direction falls outside the frame */
	project(deltaDeg: number, elevDeg: number): OverlayPoint | null;
	/** absolute azimuth → image point at the given elevation angle */
	projectAzimuth(azimuthDeg: number, elevDeg: number): OverlayPoint | null;
	/** the inverse: image pixel → the direction it looks. This is what makes
	 * "click anywhere in the photo, get the coordinates" possible — combined
	 * with the depth buffer, every pixel resolves to a real place. */
	unproject(x: number, y: number): OverlayRay;
}

/**
 * Build the fit's projection into a W×H image box.
 *
 * All three projections share px/deg = W/fov at the centre of the horizon,
 * so switching projections keeps a rough fit rather than throwing it away.
 * The vertical anchor is the warped, rolled horizon line; elevation angles
 * displace up from it.
 */
export function createOverlayProjector(fit: OverlayFit, W: number, H: number): OverlayProjector {
	const fovDeg = fit.fov_deg;
	const horizonY = (fit.horizon_pct / 100) * H;
	const pxPerDeg = (W / fovDeg) * fit.v_scale; // equirect square-pixel guess × trim
	const rollK = Math.tan((fit.roll_deg * Math.PI) / 180);
	const warp = fit.warp?.length >= 2 ? fit.warp : [0, 0];

	const hy = (x: number) => horizonY + (x - W / 2) * rollK - warpAt(warp, x / W) * pxPerDeg;

	const fovRad = (Math.min(fovDeg, 358) * Math.PI) / 180;
	const fCyl = (W / fovRad) * fit.v_scale;
	const fRectH = W / 2 / Math.tan(Math.min(fovRad, (178 * Math.PI) / 180) / 2);

	const projectRaw = (deltaDeg: number, elevDeg: number): { xb: number; dy: number } | null => {
		const a = (deltaDeg * Math.PI) / 180;
		const e = (elevDeg * Math.PI) / 180;
		switch (fit.projection) {
			case 'cylindrical':
				if (Math.abs(deltaDeg) > fovDeg / 2 + 2) return null;
				return { xb: W * (0.5 + deltaDeg / fovDeg), dy: fCyl * Math.tan(e) };
			case 'rectilinear': {
				if (Math.abs(deltaDeg) >= 89) return null;
				const xb = W / 2 + fRectH * Math.tan(a);
				if (xb < -0.1 * W || xb > 1.1 * W) return null;
				return { xb, dy: (fRectH * fit.v_scale * Math.tan(e)) / Math.cos(a) };
			}
			default: // equirect
				if (Math.abs(deltaDeg) > fovDeg / 2 + 2) return null;
				return { xb: W * (0.5 + deltaDeg / fovDeg), dy: elevDeg * pxPerDeg };
		}
	};

	const project = (deltaDeg: number, elevDeg: number): OverlayPoint | null => {
		const pt = projectRaw(deltaDeg, elevDeg);
		if (!pt) return null;
		return { x: pt.xb, y: hy(pt.xb) - pt.dy };
	};

	// the inverse of projectRaw, term for term: solve x for the azimuth delta,
	// then the vertical displacement from the (warped, rolled) horizon for the
	// elevation angle. Analytic in all three projections, no search.
	const unproject = (x: number, y: number): OverlayRay => {
		const dy = hy(x) - y;
		let deltaDeg: number;
		let elevDeg: number;
		switch (fit.projection) {
			case 'cylindrical':
				deltaDeg = (x / W - 0.5) * fovDeg;
				elevDeg = (Math.atan(dy / fCyl) * 180) / Math.PI;
				break;
			case 'rectilinear': {
				const a = Math.atan((x - W / 2) / fRectH);
				deltaDeg = (a * 180) / Math.PI;
				elevDeg =
					(Math.atan((dy * Math.cos(a)) / (fRectH * fit.v_scale)) * 180) / Math.PI;
				break;
			}
			default: // equirect
				deltaDeg = (x / W - 0.5) * fovDeg;
				elevDeg = dy / pxPerDeg;
		}
		return {
			azimuth_deg: (((fit.centre_bearing + deltaDeg) % 360) + 360) % 360,
			elev_deg: elevDeg
		};
	};

	return {
		W,
		H,
		pxPerDeg,
		horizonY: hy,
		project,
		projectAzimuth: (az, elev) => project(wrapDelta(az - fit.centre_bearing), elev),
		unproject
	};
}

// ---------------------------------------------------------------------------
// skyline extraction (the live-depth path; the baked path ships the result)
// ---------------------------------------------------------------------------

/** Minimal render-grid description the skyline needs. Structurally a subset
 * of TerrainMeta, kept separate so the baked document can carry its own. */
export interface SkylineGrid {
	width: number;
	height: number;
	elev_max_deg: number;
	elev_min_deg: number;
	depth_scale_m: number;
}

/**
 * Per column, the elevation angle of the topmost row whose terrain lies
 * within cutoffM (null cutoff = any terrain; null entry = nothing visible
 * in that column).
 *
 * Below the first terrain row, column depth is non-increasing (a lower ray
 * hits terrain at or before a higher one), so the fog crossing binary-
 * searches. Near-clip sky (0) at the bottom passes the predicate and is
 * rejected after the search.
 */
export function skylineFromDepth(
	meta: SkylineGrid,
	d: Uint16Array,
	cutoffM: number | null
): (number | null)[] {
	const step = (meta.elev_max_deg - meta.elev_min_deg) / meta.height;
	const out: (number | null)[] = new Array(meta.width).fill(null);
	const maxQ = cutoffM === null ? 0xffff : Math.floor(cutoffM / meta.depth_scale_m);
	for (let c = 0; c < meta.width; c++) {
		let r0 = -1;
		for (let r = 0; r < meta.height; r++) {
			if (d[r * meta.width + c] !== 0) {
				r0 = r;
				break;
			}
		}
		if (r0 < 0) continue;
		let lo = r0;
		if (d[r0 * meta.width + c] > maxQ) {
			let hi = meta.height;
			while (lo < hi) {
				const mid = (lo + hi) >> 1;
				if (d[mid * meta.width + c] <= maxQ) hi = mid;
				else lo = mid + 1;
			}
		}
		if (lo >= meta.height || d[lo * meta.width + c] === 0) continue;
		out[c] = meta.elev_max_deg - (lo + 0.5) * step;
	}
	return out;
}

// ---------------------------------------------------------------------------
// the baked overlay document — what graduates into hillview
// ---------------------------------------------------------------------------

/** Skyline sampled in azimuth space, independent of the render grid it came
 * from: entry i is at azimuth az_start + i·az_step. null = no terrain
 * visible (sky all the way down, or beyond the visibility cutoff). */
export interface OverlaySkyline {
	az_start: number;
	az_step: number;
	/** elevation angle per sample, degrees; null = nothing visible */
	elev_deg: (number | null)[];
	/** distance to the skyline per sample, metres; null where elev is null.
	 * Enables horizon click-back and distance shading without depth. */
	distance_m?: (number | null)[];
}

/** A labelled feature on the skyline, already visibility- and occlusion-
 * filtered against the depth buffer at export time. */
export interface OverlayLabel {
	name: string;
	lat: number;
	lon: number;
	/** elevation ANGLE of the label's anchor on the skyline, degrees (not
	 * the summit's altitude — that is `ele`) */
	elev_deg: number;
	azimuth_deg: number;
	distance_m: number;
	/** summit altitude in metres, when the source knows it */
	ele?: number | null;
	/** peak | tower | mast | city | town | village | suburb | quarter */
	kind?: string;
	prominence?: number | null;
	population?: number | null;
}

/** Provenance of the render the overlay was fitted against. */
export interface OverlayRenderRef {
	id: string;
	lat: number;
	lon: number;
	eye_elevation_m?: number;
	max_distance_m?: number;
	dsm_stack?: string;
}

/**
 * The depth buffer that came with the overlay: the render's raw uint16
 * distance grid, served as a separate (pre-gzipped) file.
 *
 * The baked skyline draws the horizon with no depth at all — this is the
 * INTERACTION layer: with it, every pixel of the photo resolves to a real
 * place, so clicking a hillside, a field or a ridge below the skyline gives
 * coordinates, not just clicking the horizon line. Fetched lazily on first
 * use (a few hundred KB over the wire, megabytes once decoded), never as
 * part of drawing.
 *
 * The grid fields are exactly TerrainMeta's, so this reference can be handed
 * straight to pickFromDepth/pickFromDepthOrHorizon.
 */
export interface OverlayDepthRef {
	/** where the bytes live (gzip-encoded uint16, row-major) */
	url: string;
	width: number;
	height: number;
	az_start: number;
	az_end: number;
	az_step_deg?: number;
	elev_max_deg: number;
	elev_min_deg: number;
	lat: number;
	lon: number;
	depth_scale_m: number;
	max_distance_m?: number;
	/** transfer size of the stored (gzipped) file, for the UI to be honest
	 * about what a click is about to download */
	bytes?: number;
}

/**
 * The graduated per-photo overlay. Stored verbatim in hillview's
 * photos.terrain_overlay and drawn by the zoom view.
 *
 * `fit` is kept canonical and untouched: the workbench decides an overlay
 * has landed by comparing exactly this sub-object against the fact it
 * exported, so anything hillview-side that adjusts the drawing must live in
 * `user_adjust` instead — otherwise a local nudge would resurrect the item
 * as a pending suggestion forever.
 */
export interface TerrainOverlay {
	version: 1;
	fit: OverlayFit;
	skyline: OverlaySkyline;
	labels: OverlayLabel[];
	render: OverlayRenderRef;
	/** the click-anywhere layer; absent when only the horizon graduated */
	depth?: OverlayDepthRef;
	/** DEM licence notice — a licence obligation, not decoration. Rides the
	 * data so an overlay keeps the notice that was true when it was made. */
	attribution: string;
	/** label-source notice (ODbL), separate so hiding labels hides it */
	label_attribution?: string;
	/** hillview-side fine-tuning, NEVER part of the graduation comparison */
	user_adjust?: OverlayUserAdjust;
	exported_at?: string;
}

/** Local adjustments applied on top of the graduated fit. */
export interface OverlayUserAdjust {
	/** shift the horizon line, percentage points of image height */
	horizon_pct_delta?: number;
}

/** The fit as actually drawn: graduated fit + any local adjustment. */
export function effectiveFit(overlay: TerrainOverlay): OverlayFit {
	const adj = overlay.user_adjust;
	if (!adj?.horizon_pct_delta) return overlay.fit;
	return { ...overlay.fit, horizon_pct: overlay.fit.horizon_pct + adj.horizon_pct_delta };
}

/** Azimuth of skyline sample i. */
export function skylineAzimuth(s: OverlaySkyline, i: number): number {
	return s.az_start + i * s.az_step;
}

/**
 * Click anywhere in the photo → the place it looks at.
 *
 * The whole point of carrying the depth buffer: unproject the pixel to a
 * ray, find that ray's cell in the render grid, and read the distance the
 * horizon march already computed there. A click above the skyline snaps DOWN
 * the column to the horizon (clicking sky means "that direction"), so a tap
 * near a ridge line still answers instead of returning nothing.
 *
 * Returns null when the pixel looks outside the rendered sector, or when the
 * whole column is sky (a direction the render never saw terrain in).
 */
export function pickFromOverlay(
	overlay: TerrainOverlay,
	depth: Uint16Array,
	x: number,
	y: number,
	W: number,
	H: number
): TerrainPick | null {
	const ref = overlay.depth;
	if (!ref) return null;
	const proj = createOverlayProjector(effectiveFit(overlay), W, H);
	const ray = proj.unproject(x, y);
	const col = colForAzimuth(ref, ray.azimuth_deg);
	if (col === null) return null;
	const step = (ref.elev_max_deg - ref.elev_min_deg) / ref.height;
	const row = Math.round((ref.elev_max_deg - ray.elev_deg) / step - 0.5);
	// above the top of the rendered band is still "look down this column"
	return pickFromDepthOrHorizon(ref, depth, col, Math.max(0, row));
}

/**
 * Project a baked skyline into image space, split into runs of consecutive
 * visible samples — the caller strokes each run as one polyline, so gaps
 * (sky columns, out-of-frame directions) break the curve instead of being
 * bridged by a false chord.
 */
export function skylinePolylines(
	skyline: OverlaySkyline,
	proj: OverlayProjector,
	fit: OverlayFit
): OverlayPoint[][] {
	const runs: OverlayPoint[][] = [];
	let cur: OverlayPoint[] = [];
	// a document without samples is a valid "nothing to draw", not a crash:
	// this runs inside the viewer's per-frame paint
	if (!skyline?.elev_deg?.length) return runs;
	for (let i = 0; i < skyline.elev_deg.length; i++) {
		const elev = skyline.elev_deg[i];
		const pt =
			elev === null || elev === undefined
				? null
				: proj.project(wrapDelta(skylineAzimuth(skyline, i) - fit.centre_bearing), elev);
		if (!pt) {
			if (cur.length > 1) runs.push(cur);
			cur = [];
			continue;
		}
		cur.push(pt);
	}
	if (cur.length > 1) runs.push(cur);
	return runs;
}
