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

/** What a label CLAIMS, derived from the evidence below — see
 * PEAK_DEPTH_REL_TOL's comment for the thresholds:
 *  summit    the pixel is the POI itself (tight depth window ∧ height band):
 *            name + elevation
 *  mass      the column sees terrain at about the POI's distance and its
 *            height, but not the summit itself — a shoulder of the same
 *            massif: name only
 *  direction a hidden but notable settlement: dim, anchored at the top
 *            edge of the terrain that hides it. Never a visibility claim. */
export type LabelClass = 'summit' | 'mass' | 'direction';

/** A peak projected into the panorama: texture coords + display facts +
 * the evidence for its class, so a GUI can reveal how much it claims. */
export interface PeakMark {
	name: string;
	u: number;
	v: number;
	distance_m: number;
	azimuth_deg: number;
	ele?: number | null;
	ele_estimated?: boolean;
	prominence?: number | null;
	kind?: string;
	population?: number | null;
	class: LabelClass;
	/** depth at the anchor pixel — what the column actually saw (m) */
	seen_m: number;
	/** metres by which the POI's own elevation angle sits ABOVE the anchor
	 * row's angle (+ = OSM ele says higher than rendered); null without an
	 * elevation or an eye height */
	dh_m: number | null;
	/** azimuth-neighbourhood column used, 0 = the node's own column */
	col_offset: number;
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

/** The visibility test and its evidence — every constant means one physical
 * thing (measured on render 252a7ea8; docs/terrain-overlay-graduation.md
 * § The label pool; mirrored by hand in enrich/api/app/overlay_export.py):
 *
 *  * WIDE depth window 8 m + 6 %·D — "the column sees terrain at about the
 *    POI's distance". 6 % is the render's own depth precision: the horizon
 *    march steps 0.5 %·d and one 0.025° row moves the ground hit-point by
 *    kilometres at grazing angles. Occlusion-safe: 98 % of what it rejects
 *    is >2 rows below the ridge by the POI's own elevation. Class MASS.
 *    Widening it does not find missed summits — it admits the famous
 *    valley towns on the ridge in front of them (a vista board, not a
 *    visibility claim); that reading is the DIRECTION class instead.
 *  * TIGHT depth window 300 m + 3 %·D — "the top edge of the terrain at the
 *    POI's distance is the summit itself". 300 m is the OSM-node-vs-
 *    rendered-summit-edge scale (near-field residual median 220 m).
 *  * HEIGHT band 100 m + ½ row — the POI's elevation angle from its ele
 *    agrees with the anchor row. In METRES, not rows: the 30 m DEM renders
 *    sharp cones 60–85 m low (Milešovka, Ještěd) and DSM canopy renders
 *    forested tops ~25 m high; both are absolute. EVERY label must pass it
 *    — measured: without it the median "mass" label sat on terrain 139 m
 *    HIGHER than the named hill, i.e. on a different landform (a 324 m
 *    hill 2 km in front of Malý Bezděz claiming Malý Bezděz's flank).
 *    Tight ∧ height ⇒ SUMMIT; wide-only ∧ height ⇒ MASS; height off ⇒
 *    hidden.
 *  * AZIMUTH neighbourhood ±50 m, at least 1 and at most 3 columns — the
 *    OSM node sits a column off the DEM summit or on a ridge edge; own
 *    column first, nearest neighbour wins.
 *  * DIRECTION — a SETTLEMENT hidden everywhere in the neighbourhood, but
 *    notable (priority ≥ 240 ≈ a town of 5 000), within 100 km, and not
 *    "behind" foreground clutter (< 1 km). Peaks are not direction
 *    material: a hidden summit is simply not in the picture.
 *  * Settlements are binary: SEEN (tight ∧ height — the DSM renders their
 *    roofs) or direction material; a hit at a town's distance at a
 *    different height is the hill behind the town. */
export const PEAK_DEPTH_REL_TOL = 0.06;
export const PEAK_DEPTH_ABS_M = 8;
export const SUMMIT_DEPTH_REL = 0.03;
export const SUMMIT_DEPTH_ABS_M = 300;
export const SUMMIT_HEIGHT_ABS_M = 100;
export const AZIMUTH_WINDOW_M = 50;
export const AZIMUTH_MAX_COLS = 3;
export const DIRECTION_MIN_PRIORITY = 240;
export const DIRECTION_MAX_DIST_M = 100_000;
export const DIRECTION_MIN_OCCLUDER_M = 1_000;
export const DEFAULT_REFRACTION_K = 0.13;
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

/** The renderer's own elevation-angle formula: atan((h − eye)/d − d/(2R'))
 * with R' = R/(1 − k). */
export function elevationAngleDeg(
	eleM: number,
	eyeM: number,
	distanceM: number,
	refractionK = DEFAULT_REFRACTION_K
): number {
	const drop = (distanceM * (1 - refractionK)) / (2 * R_EARTH_M);
	return (Math.atan((eleM - eyeM) / distanceM - drop) * 180) / Math.PI;
}

type ColumnVerdict =
	| { verdict: 'tight' | 'wide' | 'hidden'; row: number; depthM: number }
	| { verdict: 'none' };

/** Walk one column top-down. Depth is non-increasing below the skyline.
 *  tight  — first row within the tight window (summit candidate)
 *  wide   — no tight row, but a row within the wide window (mass)
 *  hidden — the profile passed D − wide without a hit; row/depth is the
 *           top edge of the terrain that hides the POI
 *  none   — all sky */
function scanColumn(
	meta: TerrainMeta,
	depth: Uint16Array,
	col: number,
	distanceM: number,
	wide: number,
	tight: number
): ColumnVerdict {
	let firstWide: { row: number; depthM: number } | null = null;
	for (let row = 0; row < meta.height; row++) {
		const q = depth[row * meta.width + col];
		if (q === 0) continue; // sky above the skyline
		const d = q * meta.depth_scale_m;
		if (Math.abs(d - distanceM) <= tight) return { verdict: 'tight', row, depthM: d };
		if (firstWide === null && Math.abs(d - distanceM) <= wide) firstWide = { row, depthM: d };
		if (d < distanceM - wide) {
			if (firstWide) return { verdict: 'wide', ...firstWide };
			return { verdict: 'hidden', row, depthM: d };
		}
	}
	if (firstWide) return { verdict: 'wide', ...firstWide };
	return { verdict: 'none' };
}

/** Every candidate gets a verdict — the labelled classes plus the reasons a
 * POI is NOT labelled — so a GUI can list the whole pool and explain why a
 * name did or did not make it. */
export type PeakVerdict =
	| LabelClass
	| 'hidden' // behind terrain (or a settlement's terrain seen but not the place)
	| 'not-notable' // hidden and below the direction threshold
	| 'too-close' // < PEAK_MIN_DISTANCE_M
	| 'out-of-range' // beyond the render's range or the kind's distance cap
	| 'outside-sweep' // bearing not covered by this render
	| 'no-terrain'; // its column is all sky (beyond the render's reach)

export interface PeakExplanation {
	peak: Peak;
	verdict: PeakVerdict;
	distance_m: number;
	azimuth_deg: number;
	priority: number;
	/** the label, when the verdict is a label class */
	mark: PeakMark | null;
	/** one sentence a person can act on */
	reason: string;
}

/** Classify one POI against the render — the full story, labelled or not.
 * Own column first, then ±1..n neighbours (AZIMUTH_WINDOW_M); the anchor is
 * the topmost pixel whose depth matches the POI's distance — the rendered
 * summit edge — which sidesteps eye/refraction bookkeeping for the anchor
 * itself; the height band then checks that edge against the POI's own
 * elevation when meta carries an eye height. `relTol` is the WIDE window's
 * relative term (the pane's slider). */
export function explainPeak(
	meta: TerrainMeta,
	depth: Uint16Array,
	peak: Peak,
	relTol = PEAK_DEPTH_REL_TOL
): PeakExplanation {
	const { bearingDeg, distanceM } = bearingDistance(meta.lat, meta.lon, peak.lat, peak.lon);
	const prio = labelPriority(peak);
	const km = (v: number) => (v >= 10000 ? `${Math.round(v / 1000)} km` : `${(v / 1000).toFixed(1)} km`);
	const base = { peak, distance_m: distanceM, azimuth_deg: bearingDeg, priority: prio, mark: null };
	if (distanceM < PEAK_MIN_DISTANCE_M)
		return { ...base, verdict: 'too-close', reason: `${km(distanceM)} away — inside the ${PEAK_MIN_DISTANCE_M} m near limit.` };
	if (typeof meta.max_distance_m === 'number' && distanceM > meta.max_distance_m)
		return { ...base, verdict: 'out-of-range', reason: `${km(distanceM)} away — beyond the render's ${km(meta.max_distance_m)} range.` };
	const kindCap = peak.kind ? PLACE_MAX_DIST_M[peak.kind] : undefined;
	if (kindCap !== undefined && distanceM > kindCap)
		return { ...base, verdict: 'out-of-range', reason: `${km(distanceM)} away — a ${peak.kind} is only labelled within ${km(kindCap)}.` };
	const col0 = colForAzimuth(meta, bearingDeg);
	if (col0 === null)
		return { ...base, verdict: 'outside-sweep', reason: `bearing ${bearingDeg.toFixed(1)}° is outside this render's sweep.` };
	const stepAz =
		meta.az_step_deg ?? (meta.width > 1 ? (meta.az_end - meta.az_start) / (meta.width - 1) : 0);
	const stepEl = (meta.elev_max_deg - meta.elev_min_deg) / meta.height;
	const wide = distanceM * relTol + PEAK_DEPTH_ABS_M;
	const tight = distanceM * SUMMIT_DEPTH_REL + SUMMIT_DEPTH_ABS_M;
	const colW = stepAz > 0 ? (distanceM * stepAz * Math.PI) / 180 : 1;
	const n = Math.min(AZIMUTH_MAX_COLS, Math.max(1, Math.round(AZIMUTH_WINDOW_M / colW)));
	const offsets = [0];
	for (let i = 1; i <= n; i++) offsets.push(i, -i);
	let best: { verdict: 'tight' | 'wide'; row: number; depthM: number; dc: number } | null = null;
	let own: ColumnVerdict | null = null;
	for (const dc of offsets) {
		const c = col0 + dc;
		if (c < 0 || c >= meta.width) continue;
		const v = scanColumn(meta, depth, c, distanceM, wide, tight);
		if (dc === 0) own = v;
		if (v.verdict === 'tight') {
			best = { verdict: 'tight', row: v.row, depthM: v.depthM, dc };
			break;
		}
		if (v.verdict === 'wide' && best === null) best = { verdict: 'wide', row: v.row, depthM: v.depthM, dc };
	}
	const isPlace = !!peak.kind && PLACE_KINDS.has(peak.kind);
	const notable = prio >= DIRECTION_MIN_PRIORITY && distanceM <= DIRECTION_MAX_DIST_M;
	let cls: LabelClass | null = null;
	let row = 0;
	let seen = 0;
	let dc = 0;
	let dh: number | null = null;
	let heightNote = '';
	if (best) {
		({ row, depthM: seen, dc } = best);
		const rowAngle = meta.elev_max_deg - (row + 0.5) * stepEl;
		if (peak.ele != null && typeof meta.eye_elevation_m === 'number') {
			const k = meta.refraction_k ?? DEFAULT_REFRACTION_K;
			const dTheta = elevationAngleDeg(peak.ele, meta.eye_elevation_m, distanceM, k) - rowAngle;
			dh = (dTheta * Math.PI * distanceM) / 180;
		}
		const band = SUMMIT_HEIGHT_ABS_M + (0.5 * stepEl * Math.PI * distanceM) / 180;
		const heightOk = dh === null || Math.abs(dh) <= band;
		if (dh !== null && !heightOk)
			heightNote = ` its elevation sits ${Math.round(Math.abs(dh))} m ${dh > 0 ? 'above' : 'below'} what is rendered there (band ±${Math.round(band)} m) — a different landform.`;
		if (best.verdict === 'tight' && heightOk) cls = 'summit';
		else if (!isPlace && heightOk) cls = 'mass';
	}
	if (cls === null) {
		// hidden — or a settlement whose column sees terrain near it but not
		// the place: "it lies in that direction, behind this"
		let occluder: number | null = null;
		if (best) occluder = best.depthM;
		else if (own && own.verdict === 'hidden') occluder = own.depthM;
		if (occluder === null)
			return { ...base, verdict: 'no-terrain', reason: `its column is all sky — nothing rendered in that direction within ${km(meta.max_distance_m ?? 0)}.` };
		const what = best
			? `terrain at ${km(occluder)} is seen near it, but not the ${isPlace ? 'place' : 'summit'} itself —${heightNote || ' its distance is off.'}`
			: `hidden behind terrain at ${km(occluder)}.`;
		if (!isPlace)
			return { ...base, verdict: 'hidden', reason: `${what} Peaks are never shown as direction hints.` };
		if (!notable)
			return { ...base, verdict: 'not-notable', reason: `${what} Direction hints need priority ≥ ${DIRECTION_MIN_PRIORITY} (this has ${Math.round(prio)}) within ${km(DIRECTION_MAX_DIST_M)}.` };
		if (occluder < DIRECTION_MIN_OCCLUDER_M)
			return { ...base, verdict: 'hidden', reason: `${what} No direction hint on foreground clutter (< ${DIRECTION_MIN_OCCLUDER_M} m).` };
		if (best) ({ row, depthM: seen, dc } = best);
		else if (own && own.verdict === 'hidden') ({ row, depthM: seen } = own), (dc = 0);
		dh = null;
		cls = 'direction';
	}
	const mark: PeakMark = {
		name: peak.name,
		u: (col0 + dc + 0.5) / meta.width,
		v: (row + 0.5) / meta.height,
		distance_m: distanceM,
		azimuth_deg: bearingDeg,
		ele: peak.ele,
		ele_estimated: peak.ele_estimated,
		prominence: peak.prominence,
		kind: peak.kind,
		population: peak.population,
		class: cls,
		seen_m: seen,
		dh_m: dh,
		col_offset: dc
	};
	return { ...base, verdict: cls, mark, reason: labelEvidence(mark) };
}

/** Project one POI into the panorama with its class and evidence, or null
 * when out of range, outside the sweep, or hidden and not notable. */
export function projectPeak(
	meta: TerrainMeta,
	depth: Uint16Array,
	peak: Peak,
	relTol = PEAK_DEPTH_REL_TOL
): PeakMark | null {
	return explainPeak(meta, depth, peak, relTol).mark;
}

/** Verdicts for the whole pool, priority order — the labelled ones first
 * (in exactly `projectPeaks` order, per-pixel cap applied: a label that lost
 * its pixel to a higher-priority one is reported as such), then the rest by
 * priority. */
export function explainPeaks(
	meta: TerrainMeta,
	depth: Uint16Array,
	peaks: Peak[],
	relTol = PEAK_DEPTH_REL_TOL
): (PeakExplanation & { kept: boolean })[] {
	const all = peaks.map((p) => explainPeak(meta, depth, p, relTol));
	const labelled = all.filter((e) => e.mark);
	labelled.sort(
		(a, b) =>
			Number(a.mark!.class === 'direction') - Number(b.mark!.class === 'direction') ||
			b.priority - a.priority ||
			Number(a.mark!.class === 'mass') - Number(b.mark!.class === 'mass') ||
			a.distance_m - b.distance_m
	);
	const seenPix = new Set<number>();
	const out: (PeakExplanation & { kept: boolean })[] = [];
	for (const e of labelled) {
		const m = e.mark!;
		const key = Math.round(m.v * meta.height - 0.5) * meta.width + Math.round(m.u * meta.width - 0.5);
		const kept = !seenPix.has(key);
		if (kept) seenPix.add(key);
		out.push(kept ? { ...e, kept } : { ...e, kept, reason: `${e.reason} Shares its depth pixel with a higher-priority label, so it is not emitted.` });
	}
	const rest = all.filter((e) => !e.mark).sort((a, b) => b.priority - a.priority || a.distance_m - b.distance_m);
	for (const e of rest) out.push({ ...e, kept: false });
	return out;
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
	// caps keep the most legible of the rest. Direction labels after every
	// visible one, so a first-come layouter never lets a hidden town
	// displace a visible summit.
	// …and among equals a confirmed SUMMIT before a mass claim (measured: two
	// foreground hills' mass claims used to outrank the real summit behind
	// them and thin it out of the layout), then nearest first
	out.sort(
		(a, b) =>
			Number(a.class === 'direction') - Number(b.class === 'direction') ||
			labelPriority(b) - labelPriority(a) ||
			Number(a.class === 'mass') - Number(b.class === 'mass') ||
			a.distance_m - b.distance_m
	);
	// one label per depth pixel: if the render cannot separate two POIs, the
	// labels must not pretend to
	const seenPix = new Set<number>();
	return out.filter((m) => {
		const key = Math.round(m.v * meta.height - 0.5) * meta.width + Math.round(m.u * meta.width - 0.5);
		if (seenPix.has(key)) return false;
		seenPix.add(key);
		return true;
	});
}

/** The facts labelText/labelEvidence read — a PeakMark, or a baked
 * OverlayLabel (whose class/evidence are optional: documents baked before
 * classes are read as 'mass', a claim no stronger than they ever made). */
export type LabelFacts = Pick<PeakMark, 'name' | 'distance_m'> &
	Partial<Pick<PeakMark, 'kind' | 'ele' | 'ele_estimated' | 'class' | 'seen_m' | 'dh_m' | 'col_offset'>>;

/** The text a label shows, by what it claims: summit → name + elevation
 * (only an OSM elevation — a DEM-filled one is not the summit's), mass →
 * name, direction → name (drawn dim by the painter). Places never show an
 * elevation. */
export function labelText(m: LabelFacts, opts: { km?: boolean } = {}): string {
	const isPlace = !!m.kind && PLACE_KINDS.has(m.kind);
	let t = m.name;
	if (m.class === 'summit' && !isPlace && m.ele != null && !m.ele_estimated)
		t += ` ${Math.round(m.ele)}`;
	if (opts.km && m.class !== 'direction') {
		const km = m.distance_m / 1000;
		t += ` · ${km >= 10 ? Math.round(km) : km.toFixed(1)} km`;
	}
	return t;
}

/** One sentence of evidence for a label — what the column saw versus what
 * was computed — for a hover / tap detail. */
export function labelEvidence(m: LabelFacts): string {
	const km = (v: number) => (v >= 10000 ? `${Math.round(v / 1000)} km` : `${(v / 1000).toFixed(1)} km`);
	if (m.seen_m == null) return `Terrain in its direction at about ${km(m.distance_m)} (baked before evidence was recorded).`;
	const off = m.col_offset ? ` (${Math.abs(m.col_offset)} column${Math.abs(m.col_offset) > 1 ? 's' : ''} ${m.col_offset > 0 ? 'right' : 'left'} of its bearing)` : '';
	const height = m.dh_m == null ? '' : `, its elevation ${Math.abs(m.dh_m) < 1 ? 'agrees' : `sits ${Math.round(Math.abs(m.dh_m))} m ${m.dh_m > 0 ? 'above' : 'below'} what is rendered`}`;
	switch (m.class ?? 'mass') {
		case 'summit':
			return `Summit seen: terrain at ${km(m.seen_m)}, computed ${km(m.distance_m)}${height}${off}.`;
		case 'mass':
			return `Terrain at ${km(m.seen_m)} in its direction (computed ${km(m.distance_m)})${height}${off} — the massif, not confirmed as the summit.`;
		default:
			return `Hidden: lies ${km(m.distance_m)} away, behind terrain at ${km(m.seen_m)}.`;
	}
}

/** Sky-anchored label layout, vista-board style: each label is a SLAT that
 * starts just above its summit and runs up-right at `angleDeg` (default 45°),
 * so parallel slats tile like the slats of a blind and never collide however
 * long the names are — the only constraint is anchor spacing,
 * Δx·sin θ ≥ pillH + gap. That is what lets a horizon carry ~2× the labels
 * of horizontal pills without any stacking, and it keeps left-to-right
 * reading order equal to azimuth order. `angleDeg = 0` is a horizontal,
 * non-stacking layout (the next anchor must clear the previous label's end).
 *
 * Input order = priority (feed prominence-first). Selection is FIRST-COME:
 * a label whose slat would overlap an already accepted one is skipped —
 * the best name wins its neighbourhood instead of a global cap letting far
 * famous peaks displace everything near (measured: that made the tolerance
 * slider FEEL inverted). `minGapX` is an optional extra floor on anchor
 * spacing on top of the geometry. A label whose slat would START above the
 * canvas top is dropped (nothing of it would show); one that merely runs
 * off the top or right edge is kept and clipped by the canvas.
 *
 * Geometry (screen coordinates, y down): anchor A = (cx, cy); origin
 * O = (cx, cy − leader); axis direction u = (cos θ, −sin θ); the pill is the
 * rectangle along the axis from O for `pillW`, thickness `pillH` on the
 * upper-left side of the axis. Painters translate to O and rotate by −θ;
 * `hitSkyLabel` inverse-rotates the tap. Pure and painter-agnostic. */
export interface SkyLabel {
	label: string;
	cx: number;
	cy: number; // anchor (summit) in canvas px
	pillW: number; // pill length along its axis
	pillH: number; // pill thickness
	/** slat angle, radians, 0 = horizontal, positive = up-right */
	angle: number;
	/** pill origin — the axis start, where the leader ends */
	ox: number;
	oy: number;
	id?: string;
}

export interface SkyLabelInput {
	label: string;
	cx: number;
	cy: number;
	pillW: number;
	id?: string;
}

export interface SkyLayoutOptions {
	pillH?: number;
	gap?: number;
	leader?: number;
	minGapX?: number;
	/** slat angle in degrees, 0..90; default 45 */
	angleDeg?: number;
}

export const SKY_LABEL_ANGLE_DEG = 45;

/** Do two same-angle pills overlap? Parallel rectangles: overlap iff their
 * projections overlap along BOTH the axis (u) and the normal (n). */
function slatsOverlap(a: SkyLabel, b: SkyLabel, gap: number): boolean {
	const cos = Math.cos(a.angle);
	const sin = Math.sin(a.angle);
	const dx = b.ox - a.ox;
	const dy = b.oy - a.oy;
	const along = dx * cos - dy * sin; // b's origin in a's axis frame
	const across = dx * sin + dy * cos; // + = down-right of a's axis
	const alongOverlap = along < a.pillW + gap && along + b.pillW > -gap;
	// a's band spans across ∈ [−pillH, 0]; b's spans [across − pillH, across]
	const acrossOverlap = across < a.pillH + gap && across > -(b.pillH + gap);
	return alongOverlap && acrossOverlap;
}

/** Extra input fields (kind, class, mark, …) ride through to the placed
 * pills, so a painter can style by what the label claims. */
export function layoutSkyLabels<T extends SkyLabelInput>(
	inputs: T[],
	W: number,
	H: number,
	opts: SkyLayoutOptions = {}
): (T & SkyLabel)[] {
	const pillH = opts.pillH ?? 20;
	const gap = opts.gap ?? 3;
	const leader = opts.leader ?? 12;
	const minGapX = opts.minGapX ?? 0;
	const angle = ((opts.angleDeg ?? SKY_LABEL_ANGLE_DEG) * Math.PI) / 180;
	const placed: (T & SkyLabel)[] = [];
	for (const i of inputs) {
		if (i.cx < 0 || i.cx > W || i.cy < 0 || i.cy > H) continue;
		const c: T & SkyLabel = { ...i, pillH, angle, ox: i.cx, oy: i.cy - leader };
		// nothing of a slat that starts above the top edge would show
		if (c.oy - pillH * Math.cos(angle) < 2) continue;
		if (placed.some((p) => Math.abs(p.cx - c.cx) < minGapX || slatsOverlap(p, c, gap))) continue;
		placed.push(c);
	}
	return placed;
}

/** Hit test a tap against placed sky labels (slop widens the target for
 * touch): the tap is inverse-rotated into each pill's frame. First match
 * wins — placed order is priority order. */
export function hitSkyLabel<T extends SkyLabel>(
	placed: T[],
	x: number,
	y: number,
	slop = 4
): T | null {
	for (const l of placed) {
		const cos = Math.cos(l.angle);
		const sin = Math.sin(l.angle);
		const dx = x - l.ox;
		const dy = y - l.oy;
		const along = dx * cos - dy * sin;
		const across = dx * sin + dy * cos;
		if (along >= -slop && along <= l.pillW + slop && across <= slop && across >= -l.pillH - slop)
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
