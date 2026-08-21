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
export { isDepthBlob, parseDepthBlob, DEPTH_BLOB_HEADER_BYTES, DEPTH_BLOB_VERSION } from './depthPanoViewer';
import { colForAzimuth, type LabelClass } from './peakLabels';

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
	/** Handle positions as fractions of the width, ascending, one per `warp`
	 * entry (default: equally spaced). Put them ON THE SEAMS of a stitched
	 * pano: every per-segment quantity below refers to the panel between two
	 * consecutive knots. Absent = equal spacing. */
	knots?: number[];
	/** HORIZONTAL (azimuth) shift per SEGMENT: `hwarp[k]` is the azimuth
	 * offset in DEGREES of the whole panel between knots k and k+1 — the pano
	 * shows an azimuth this much HIGHER there than the ideal projection says
	 * (positive = the content sits left of where the model expects it).
	 * Piecewise CONSTANT, not interpolated: a stitching seam is a step and a
	 * mis-stitched panel is shifted whole, not stretched. Same length as
	 * `warp`; the last entry has no segment and is ignored. Absent (or all
	 * zero) = none. */
	hwarp?: number[];
	/** SCALE per SEGMENT: `hscale[k]` > 1 means the panel between knots k
	 * and k+1 was rendered that much LARGER than the ideal projection (a
	 * frame stitched with a wrong focal length), about the panel's centre,
	 * in BOTH axes — the vertical px/deg of that panel scales with it. Same
	 * length as `warp`; last entry ignored. Absent (or all 1) = none. */
	hscale?: number[];
	/** atmospheric visibility read off the photo, km; null/absent = full
	 * render range. A hard distance cutoff, not a shading term — the DEFAULT
	 * the viewer opens with (the baked skyline is cut here). */
	visibility_km?: number | null;
	/** how far the baked document reaches, km: labels are baked out to this
	 * (capped by the render's range) so a viewer's fog slider has room above
	 * the default without a re-export. Absent = DEFAULT_MAX_VISIBILITY_KM. */
	max_visibility_km?: number | null;
	/** client wall-clock of the change (epoch ms) — drafts/live state only;
	 * facts stay timestamp-free, being content-addressed. */
	saved_at?: number;
}

/** Range the export bakes labels to when the fit does not say (km). */
export const DEFAULT_MAX_VISIBILITY_KM = 150;

/** Signed angle difference in (-180, 180]. */
export function wrapDelta(d: number): number {
	return ((((d + 180) % 360) + 360) % 360) - 180;
}

/** Equally spaced knots for n handles. */
export function uniformKnots(n: number): number[] {
	if (n < 2) return [0, 1];
	return Array.from({ length: n }, (_, i) => i / (n - 1));
}

/** The knots a fit uses: its own when valid (n ascending fractions), else
 * equal spacing. */
export function knotsOf(fit: { warp: number[]; knots?: number[] }): number[] {
	const n = Math.max(2, fit.warp?.length ?? 2);
	const k = fit.knots;
	if (k && k.length === n && k.every((v, i) => (i === 0 || v >= k[i - 1]) && v >= 0 && v <= 1))
		return k;
	return uniformKnots(n);
}

/** Index of the segment (0..n−2) containing horizontal fraction `frac`;
 * the outer segments extend beyond the frame. */
export function segmentAt(knots: number[], frac: number): number {
	const n = knots.length;
	if (n < 2) return 0;
	let k = 0;
	while (k < n - 2 && frac >= knots[k + 1]) k++;
	return k;
}

/** Warp offset (degrees, + = up) at horizontal fraction 0..1 — piecewise
 * linear between the knots (equal spacing when none are given). */
export function warpAt(warp: number[], frac: number, knots?: number[]): number {
	const n = warp.length;
	if (!n) return 0;
	if (n === 1) return warp[0];
	const kn = knots && knots.length === n ? knots : uniformKnots(n);
	const f = Math.min(1, Math.max(0, frac));
	const k = segmentAt(kn, f);
	const span = kn[k + 1] - kn[k];
	const t = span > 0 ? Math.min(1, Math.max(0, (f - kn[k]) / span)) : 0;
	return warp[k] + (warp[k + 1] - warp[k]) * t;
}

/** Segment shift at horizontal fraction 0..1: `hwarp[k]` for the segment
 * that contains it (piecewise constant, a step at each knot). */
export function hstepAt(hwarp: number[], frac: number, knots?: number[]): number {
	const n = hwarp.length;
	if (n < 2) return n === 1 ? hwarp[0] : 0;
	const kn = knots && knots.length === n ? knots : uniformKnots(n);
	return hwarp[segmentAt(kn, frac)];
}

/** Change segment count for a piecewise-constant per-segment array (shift
 * or scale), keeping each new segment the value of the old segment its
 * midpoint falls in. `fill` is the neutral value (0 for shifts, 1 for
 * scales). */
export function resampleSteps(old: number[], n: number, fill = 0, oldKnots?: number[]): number[] {
	if (n < 2) return [fill, fill];
	if (old.length < 2) return new Array(n).fill(fill);
	const out = new Array(n).fill(fill);
	for (let k = 0; k < n - 1; k++) out[k] = hstepAt(old, (k + 0.5) / (n - 1), oldKnots);
	return out;
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
	// the handle count is the longest of the per-handle arrays (they should
	// agree; a shorter one is padded with its neutral value so a fit that
	// carries, say, more shift entries than warp entries still applies)
	const n = Math.max(2, fit.warp?.length ?? 0, fit.hwarp?.length ?? 0, fit.hscale?.length ?? 0, fit.knots?.length ?? 0);
	const pad = (a: number[] | undefined, fill: number) =>
		Array.from({ length: n }, (_, i) => (a && i < a.length ? a[i] : fill));
	const warp = pad(fit.warp?.length ? fit.warp : [0, 0], 0);
	const knots = knotsOf({ warp, knots: fit.knots });
	// per-segment stitch model: shift (degrees) and scale (about the panel's
	// centre, both axes) of the panel between knots k and k+1
	const shifts = pad(fit.hwarp, 0);
	const scales = pad(fit.hscale, 1);
	const stitched = shifts.some((v) => v !== 0) || scales.some((v, i) => i < n - 1 && v !== 1);
	const segAt = (x: number) => segmentAt(knots, x / W);
	const segCentre = (k: number) => ((knots[k] + knots[k + 1]) / 2) * W;
	const scaleAt = (x: number) => (stitched ? scales[segAt(x)] : 1);

	const hy = (x: number) =>
		horizonY + (x - W / 2) * rollK - warpAt(warp, x / W, knots) * pxPerDeg * scaleAt(x);

	// a stitched pano may exceed 360° by its closing overlap: the cylinder's
	// px-per-radian is simply W over the full sweep (no clamp — that would
	// mis-scale the vertical); only the rectilinear tan needs its guard
	const fovRad = (fovDeg * Math.PI) / 180;
	const fCyl = (W / fovRad) * fit.v_scale;
	const fRectH = W / 2 / Math.tan(Math.min(fovRad, (178 * Math.PI) / 180) / 2);
	const rect = fit.projection === 'rectilinear';
	const cyl = fit.projection === 'cylindrical';

	// the IDEAL projection's azimuth↔x, per projection (no warp)
	const xIdeal = (deltaDeg: number): number =>
		rect ? W / 2 + fRectH * Math.tan((deltaDeg * Math.PI) / 180) : W * (0.5 + deltaDeg / fovDeg);
	const deltaIdeal = (x: number): number =>
		rect ? (Math.atan((x - W / 2) / fRectH) * 180) / Math.PI : (x / W - 0.5) * fovDeg;
	// vertical scale is the ideal geometry's at that x (rectilinear stretches
	// off-axis by 1/cos of the ideal angle there), times the panel's scale
	const dyAt = (x: number, elevDeg: number): number => {
		const e = (elevDeg * Math.PI) / 180;
		const sc = scaleAt(x);
		if (cyl) return fCyl * Math.tan(e) * sc;
		if (rect) return ((fRectH * fit.v_scale * Math.tan(e)) / Math.cos(Math.atan((x - W / 2) / fRectH))) * sc;
		return elevDeg * pxPerDeg * sc;
	};

	// panel k renders true azimuth `delta` at the ideal x of the azimuth
	// c_k + (delta − shift_k − c_k)·scale_k, where c_k is the ideal azimuth of
	// the panel's centre: scaled about its centre, then shifted whole
	const panelDelta = (k: number, deltaDeg: number): number => {
		const c = deltaIdeal(segCentre(k));
		return c + (deltaDeg - shifts[k] - c) * scales[k];
	};
	const trueDelta = (k: number, x: number): number => {
		const c = deltaIdeal(segCentre(k));
		return c + (deltaIdeal(x) - c) / scales[k] + shifts[k];
	};

	/** image x where azimuth delta appears: without a stitch model, the ideal
	 * x; with one, the first panel (left→right) in which the panel's mapping
	 * puts it. Panels are rigid pieces, so an azimuth can fall in a seam GAP
	 * (nowhere: null — the pano really does not show it) or in an OVERLAP
	 * (twice: the left one wins). The outer panels extend beyond the frame so
	 * points just outside it still project, as before. */
	const xOf = (deltaDeg: number): number | null => {
		if (!stitched) return xIdeal(deltaDeg);
		for (let k = 0; k < n - 1; k++) {
			const x = xIdeal(panelDelta(k, deltaDeg));
			const lo = k === 0 ? -Infinity : knots[k] * W;
			const hi = k === n - 2 ? Infinity : knots[k + 1] * W;
			if (x >= lo && x < hi) return x;
		}
		return null;
	};

	const project = (deltaDeg: number, elevDeg: number): OverlayPoint | null => {
		if (rect ? Math.abs(deltaDeg) >= 89 : Math.abs(deltaDeg) > fovDeg / 2 + 2) return null;
		const x = xOf(deltaDeg);
		if (x === null) return null;
		if (rect && (x < -0.1 * W || x > 1.1 * W)) return null;
		return { x, y: hy(x) - dyAt(x, elevDeg) };
	};

	// the inverse, term for term: the ideal azimuth at x plus the horizontal
	// warp there, then the vertical displacement from the (warped, rolled)
	// horizon for the elevation angle. Analytic in all three projections.
	const unproject = (x: number, y: number): OverlayRay => {
		const dy = hy(x) - y;
		const deltaDeg = stitched ? trueDelta(segAt(x), x) : deltaIdeal(x);
		const sc = scaleAt(x);
		let elevDeg: number;
		if (cyl) elevDeg = (Math.atan(dy / (fCyl * sc)) * 180) / Math.PI;
		else if (rect) {
			const a = Math.atan((x - W / 2) / fRectH);
			elevDeg = (Math.atan((dy * Math.cos(a)) / (fRectH * fit.v_scale * sc)) * 180) / Math.PI;
		} else elevDeg = dy / (pxPerDeg * sc);
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
	/** true when ele was DEM-filled (no OSM tag) — never printed as the summit's */
	ele_estimated?: boolean;
	/** peak | tower | mast | city | town | village | suburb | quarter */
	kind?: string;
	prominence?: number | null;
	population?: number | null;
	/** what the label claims (peakLabels.LabelClass); documents baked before
	 * classes carry none — treat as 'mass' */
	class?: LabelClass;
	/** evidence — see peakLabels.PeakMark */
	seen_m?: number;
	dh_m?: number | null;
	col_offset?: number;
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
	/** how far the labels were actually baked, km (max_visibility capped by
	 * the render's range) — the ceiling for a viewer's fog slider; absent on
	 * documents baked before it existed (their labels reach the fit's
	 * visibility only) */
	labels_cutoff_km?: number;
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

/** The fog a viewer opens with (km) and the farthest fog its slider can
 * offer with labels present: default = the fit's visibility (else the label
 * cutoff, else null = everything baked), max = the label cutoff (else the
 * fit's visibility, else the depth range). */
export function fogBounds(overlay: TerrainOverlay): { defaultKm: number | null; maxKm: number | null } {
	const fit = overlay.fit;
	const labelsKm = overlay.labels_cutoff_km ?? null;
	const depthKm = overlay.depth?.max_distance_m != null ? overlay.depth.max_distance_m / 1000 : null;
	const defaultKm = fit.visibility_km ?? labelsKm ?? null;
	const maxKm = labelsKm ?? fit.visibility_km ?? depthKm ?? null;
	return { defaultKm, maxKm };
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
