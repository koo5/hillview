import { describe, expect, it } from 'vitest';
import type { TerrainMeta } from './depthPanoViewer';
import { destinationPoint } from './depthPanoViewer';
import {
	bearingDistance,
	colForAzimuth,
	explainPeak,
	explainPeaks,
	hitSkyLabel,
	labelEvidence,
	labelPriority,
	labelText,
	layoutSkyLabels,
	projectPeak,
	projectPeaks,
	texToCanvas,
	type Peak
} from './peakLabels';

// 360 columns of 1° (centers 0.5..359.5), 20 rows over +10..-10°, 10 m quanta
const meta: TerrainMeta = {
	width: 360, height: 20,
	az_start: 0.5, az_end: 359.5, az_step_deg: 1.0,
	elev_max_deg: 10, elev_min_deg: -10,
	lat: 50.0, lon: 14.5, depth_scale_m: 10, max_distance_m: 100_000
};

/** column profile: rows 0..skyTop-1 sky, then given depths (m) downward,
 * remaining rows repeating the last depth */
function makeDepth(columns: Record<number, { skyTop: number; depths: number[] }>): Uint16Array {
	const d = new Uint16Array(meta.width * meta.height);
	for (const [colStr, prof] of Object.entries(columns)) {
		const col = Number(colStr);
		for (let row = prof.skyTop; row < meta.height; row++) {
			const m = prof.depths[Math.min(row - prof.skyTop, prof.depths.length - 1)];
			d[row * meta.width + col] = Math.round(m / meta.depth_scale_m);
		}
	}
	return d;
}

function peakAt(azimuthDeg: number, distanceM: number, name = 'Peak'): Peak {
	const p = destinationPoint(meta.lat, meta.lon, azimuthDeg, distanceM);
	return { name, lat: p.lat, lon: p.lon, ele: 1000 };
}

describe('bearingDistance inverts destinationPoint', () => {
	it('round-trips bearing and distance on the shared sphere', () => {
		const p = destinationPoint(meta.lat, meta.lon, 123.4, 42_000);
		const { bearingDeg, distanceM } = bearingDistance(meta.lat, meta.lon, p.lat, p.lon);
		expect(bearingDeg).toBeCloseTo(123.4, 3);
		expect(distanceM).toBeCloseTo(42_000, 0);
	});
});

describe('colForAzimuth inverts azimuthForColumn', () => {
	it('maps column-center azimuths back to their columns', () => {
		expect(colForAzimuth(meta, 0.5)).toBe(0);
		expect(colForAzimuth(meta, 90.5)).toBe(90);
		expect(colForAzimuth(meta, 359.5)).toBe(359);
	});
});

describe('projectPeak — visibility straight from the depth buffer', () => {
	it('labels a peak at the skyline: topmost matching row', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		const m = projectPeak(meta, depth, peakAt(90.5, 20_000))!;
		expect(m).not.toBeNull();
		expect(m.u).toBeCloseTo((90 + 0.5) / 360, 9);
		expect(m.v).toBeCloseTo((5 + 0.5) / 20, 9);
		expect(m.distance_m).toBeCloseTo(20_000, -1);
	});

	it('occluded by a nearer ridge → no label (no depth ever matches)', () => {
		const depth = makeDepth({ 90: { skyTop: 3, depths: [500] } });
		expect(projectPeak(meta, depth, peakAt(90.5, 20_000))).toBeNull();
	});

	it('visible in front of a higher, farther ridge: scan walks down past the background', () => {
		const depth = makeDepth({
			90: { skyTop: 2, depths: [80_000, 80_000, 80_000, 20_000, 20_000] }
		});
		const m = projectPeak(meta, depth, peakAt(90.5, 20_000))!;
		expect(m).not.toBeNull();
		expect(m.v).toBeCloseTo((5 + 0.5) / 20, 9); // rows 2..4 background, 5 = summit
	});

	it('relTol widens/narrows the depth match (the pane slider)', () => {
		// rendered surface at 22 km, peak at 20 km: 10% off
		const depth = makeDepth({ 90: { skyTop: 5, depths: [22_000] } });
		const peak = peakAt(90.5, 20_000);
		expect(projectPeak(meta, depth, peak)).toBeNull(); // default 6% rejects
		expect(projectPeak(meta, depth, peak, 0.15)).not.toBeNull(); // loose accepts
		expect(projectPeak(meta, depth, peak, 0.01)).toBeNull(); // strict rejects
	});

	it('respects range and the minimum distance', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		expect(projectPeak(meta, depth, peakAt(90.5, 200_000))).toBeNull(); // beyond max
		expect(projectPeak(meta, depth, peakAt(90.5, 300))).toBeNull(); // too close
	});

	it('projectPeaks filters and sorts nearest-first', () => {
		const depth = makeDepth({
			90: { skyTop: 5, depths: [20_000] },
			180: { skyTop: 7, depths: [60_000] },
			270: { skyTop: 3, depths: [400] } // occluder
		});
		const marks = projectPeaks(meta, depth, [
			peakAt(180.5, 60_000, 'Far'),
			peakAt(90.5, 20_000, 'Near'),
			peakAt(270.5, 50_000, 'Hidden')
		]);
		expect(marks.map((m) => m.name)).toEqual(['Near', 'Far']);
	});

	it('prominence-tagged peaks outrank nearer untagged ones', () => {
		const depth = makeDepth({
			90: { skyTop: 5, depths: [20_000] },
			180: { skyTop: 7, depths: [60_000] }
		});
		const famous = { ...peakAt(180.5, 60_000, 'Famous'), prominence: 232 };
		const marks = projectPeaks(meta, depth, [peakAt(90.5, 20_000, 'Near'), famous]);
		expect(marks.map((m) => m.name)).toEqual(['Famous', 'Near']);
		expect(marks[0].prominence).toBe(232);
	});
});

// the same grid with an eye height, so the height band is testable. Row 5
// (centre +4.5°) at 20 km ⇔ ele ≈ 1901 m for eye 300 m, k 0.13.
const metaEye: TerrainMeta = { ...meta, eye_elevation_m: 300, refraction_k: 0.13 };
const peakEle = (az: number, d: number, name: string, ele: number, extra: Partial<Peak> = {}): Peak => ({
	...peakAt(az, d, name),
	ele,
	...extra
});

describe('label classes — what a label claims, and its evidence', () => {
	it('summit needs the tight depth window AND the height band (in metres)', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		const agrees = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1901))!;
		expect(agrees.class).toBe('summit');
		expect(Math.abs(agrees.dh_m!)).toBeLessThan(15);
		expect(agrees.seen_m).toBe(20_000);
		expect(agrees.col_offset).toBe(0);
		// ele says the summit is ~1.1 km higher than the rendered edge: a
		// different landform — not shown, and the explanation says why
		expect(projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 3000))).toBeNull();
		const why = explainPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 3000));
		expect(why.verdict).toBe('hidden');
		expect(why.reason).toMatch(/different landform/);
	});

	it('wide window only → mass, carrying what was actually seen', () => {
		// 21 km: outside 300 m + 3 % (900 m), inside 8 m + 6 % (1208 m)
		const depth = makeDepth({ 90: { skyTop: 5, depths: [21_000] } });
		const m = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1901))!;
		expect(m.class).toBe('mass');
		expect(m.seen_m).toBe(21_000);
		expect(m.distance_m).toBeCloseTo(20_000, 0);
		// …but mass needs the height band too: a hill far below the terrain
		// seen near it is a different landform, not its mass
		expect(projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 500))).toBeNull();
	});

	it('a summit outranks a mass claim of equal priority', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [21_000] }, 91: { skyTop: 5, depths: [21_000] } });
		const marks = projectPeaks(metaEye, depth, [
			peakEle(90.5, 20_000, 'Kopec', 1901), // wide only → mass, nearer
			peakEle(91.5, 21_000, 'Vrch', 1901 + 60) // tight → summit
		]);
		expect(marks.map((m) => [m.name, m.class])).toEqual([
			['Vrch', 'summit'],
			['Kopec', 'mass']
		]);
	});

	it('a tight row below a wide-only skyline row is the anchor', () => {
		const depth = makeDepth({ 90: { skyTop: 4, depths: [21_000, 21_000, 20_000] } });
		// ele ≈ 1551 m puts the summit's angle at row 6 (+3.5°) for eye 300 m
		const m = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1551))!;
		expect(m.seen_m).toBe(20_000);
		expect(m.v).toBeCloseTo((6 + 0.5) / meta.height, 6);
		expect(m.class).toBe('summit');
	});

	it('without an eye height, tight alone makes a summit', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		const m = projectPeak(meta, depth, peakEle(90.5, 20_000, 'Vrch', 3000))!;
		expect(m.class).toBe('summit');
		expect(m.dh_m).toBeNull();
	});

	it('a hidden notable settlement → direction, anchored at the top edge of the occluder', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [5_000] } });
		const town = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Town', 200, { kind: 'town', population: 40_000 }))!;
		expect(town.class).toBe('direction');
		expect(town.seen_m).toBe(5_000);
		expect(town.v).toBeCloseTo((5 + 0.5) / meta.height, 6);
		// a small village is dropped; a hidden PEAK is never direction material
		expect(projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Ves', 200, { kind: 'village', population: 300 }))).toBeNull();
		expect(projectPeak(metaEye, depth, { ...peakAt(90.5, 20_000, 'Big'), prominence: 900 })).toBeNull();
		// beyond 100 km no direction hint; nor behind foreground clutter
		const far = { ...metaEye, max_distance_m: 200_000 };
		expect(projectPeak(far, depth, peakEle(90.5, 150_000, 'City', 200, { kind: 'city', population: 500_000 }))).toBeNull();
		const tree = makeDepth({ 90: { skyTop: 0, depths: [100] } });
		expect(projectPeak(metaEye, tree, peakEle(90.5, 20_000, 'City', 200, { kind: 'city', population: 500_000 }))).toBeNull();
	});

	it('a settlement is seen or a direction hint — never mass', () => {
		const near = makeDepth({ 90: { skyTop: 5, depths: [21_000] } });
		const town = peakEle(90.5, 20_000, 'Town', 200, { kind: 'town', population: 40_000 });
		expect(projectPeak(metaEye, near, town)!.class).toBe('direction');
		const village = peakEle(90.5, 20_000, 'Ves', 200, { kind: 'village', population: 300 });
		expect(projectPeak(metaEye, near, village)).toBeNull();
		const exact = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		expect(projectPeak(metaEye, exact, peakEle(90.5, 20_000, 'Town', 3000, { kind: 'town', population: 40_000 }))!.class).toBe('direction');
		expect(projectPeak(metaEye, exact, peakEle(90.5, 20_000, 'Town', 1901, { kind: 'town', population: 40_000 }))!.class).toBe('summit');
	});

	it('direction labels sort after every visible one', () => {
		const depth = makeDepth({
			89: { skyTop: 5, depths: [5_000] },
			90: { skyTop: 5, depths: [5_000] },
			91: { skyTop: 5, depths: [5_000] },
			180: { skyTop: 5, depths: [20_000] }
		});
		const marks = projectPeaks(metaEye, depth, [
			peakEle(90.5, 20_000, 'City', 200, { kind: 'city', population: 500_000 }),
			{ ...peakEle(180.5, 20_000, 'Small', 1901), prominence: 10 }
		]);
		expect(marks.map((m) => [m.name, m.class])).toEqual([
			['Small', 'summit'],
			['City', 'direction']
		]);
	});

	it('azimuth neighbourhood rescues a node one column off its summit', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [5_000] }, 91: { skyTop: 5, depths: [20_000] } });
		const m = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Edge', 1901))!;
		expect(m.col_offset).toBe(1);
		expect(m.class).toBe('summit');
		expect(m.u).toBeCloseTo((91 + 0.5) / meta.width, 6);
	});

	it('one label per depth pixel keeps the higher priority', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		const marks = projectPeaks(metaEye, depth, [
			peakEle(90.5, 20_000, 'Turm A', 1901),
			{ ...peakEle(90.5, 20_000, 'Turm B', 1901), prominence: 40 }
		]);
		expect(marks.map((m) => m.name)).toEqual(['Turm B']);
	});

	it('labelText: elevation only for a summit with an OSM elevation; places never', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] } });
		const summit = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1901))!;
		expect(labelText(summit)).toBe('Vrch 1901');
		expect(labelText(summit, { km: true })).toBe('Vrch 1901 · 20 km');
		const est = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1901, { ele_estimated: true }))!;
		expect(labelText(est)).toBe('Vrch');
		const mass = projectPeak(metaEye, makeDepth({ 90: { skyTop: 5, depths: [21_000] } }), peakEle(90.5, 20_000, 'Vrch', 1901))!;
		expect(mass.class).toBe('mass');
		expect(labelText(mass, { km: true })).toBe('Vrch · 20 km');
		const town = projectPeak(metaEye, depth, peakEle(90.5, 20_000, 'Town', 1901, { kind: 'town', population: 40_000 }))!;
		expect(labelText(town)).toBe('Town');
		const hidden = projectPeak(metaEye, makeDepth({ 90: { skyTop: 5, depths: [5_000] } }), peakEle(90.5, 20_000, 'Big', 200, { kind: 'town', population: 40_000 }))!;
		expect(labelText(hidden, { km: true })).toBe('Big');
		expect(labelEvidence(hidden)).toMatch(/Hidden.*behind terrain at 5\.0 km/);
		expect(labelEvidence(summit)).toMatch(/Summit seen/);
		expect(labelEvidence(mass)).toMatch(/not confirmed as the summit/);
	});
});

describe('explainPeak — a verdict and a reason for every candidate', () => {
	const depth = makeDepth({ 90: { skyTop: 5, depths: [20_000] }, 180: { skyTop: 5, depths: [5_000] } });

	it('labelled classes come with their evidence sentence and a mark', () => {
		const e = explainPeak(metaEye, depth, peakEle(90.5, 20_000, 'Vrch', 1901));
		expect(e.verdict).toBe('summit');
		expect(e.mark?.class).toBe('summit');
		expect(e.reason).toMatch(/Summit seen/);
	});

	it('names the gate that stopped a candidate', () => {
		expect(explainPeak(metaEye, depth, peakAt(90.5, 300)).verdict).toBe('too-close');
		expect(explainPeak(metaEye, depth, peakAt(90.5, 200_000)).verdict).toBe('out-of-range');
		expect(explainPeak(metaEye, depth, peakEle(90.5, 50_000, 'Ves', 200, { kind: 'village', population: 300 })).verdict).toBe('out-of-range');
		// hidden peak: behind terrain, and peaks are never direction hints
		const hid = explainPeak(metaEye, depth, { ...peakAt(180.5, 20_000, 'Big'), prominence: 900 });
		expect(hid.verdict).toBe('hidden');
		expect(hid.reason).toMatch(/hidden behind terrain at 5\.0 km/);
		// hidden small village: below the direction threshold, and says so
		const ves = explainPeak(metaEye, depth, peakEle(180.5, 20_000, 'Ves', 200, { kind: 'village', population: 300 }));
		expect(ves.verdict).toBe('not-notable');
		expect(ves.reason).toMatch(/priority ≥ 240/);
		// all-sky column
		expect(explainPeak(metaEye, depth, peakAt(45.5, 20_000)).verdict).toBe('no-terrain');
	});

	it('explainPeaks lists labelled first in projectPeaks order, marks pixel losers, then the rest', () => {
		const out = explainPeaks(metaEye, depth, [
			peakEle(90.5, 20_000, 'Turm A', 1901),
			{ ...peakEle(90.5, 20_000, 'Turm B', 1901), prominence: 40 },
			{ ...peakAt(180.5, 20_000, 'Big'), prominence: 900 },
			peakAt(90.5, 300, 'Near')
		]);
		expect(out.map((e) => [e.peak.name, e.verdict, e.kept])).toEqual([
			['Turm B', 'summit', true],
			['Turm A', 'summit', false],
			['Big', 'hidden', false],
			['Near', 'too-close', false]
		]);
		expect(out[1].reason).toMatch(/Shares its depth pixel/);
	});
});

describe('settlement place names as label candidates', () => {
	it('labelPriority: population log-maps into prominence-like metres', () => {
		expect(labelPriority({ kind: 'city', population: 1_000_000 })).toBeCloseTo(450, 0);
		expect(labelPriority({ kind: 'town', population: 10_000 })).toBeCloseTo(270, 0);
		expect(labelPriority({ kind: 'village', population: null })).toBe(0);
		expect(labelPriority({ kind: 'village', population: 5 })).toBe(0); // never negative
		expect(labelPriority({ prominence: 232 })).toBe(232); // peaks unchanged
	});

	it('per-kind distance caps: a village beyond 30 km drops, a city never', () => {
		const depth = makeDepth({ 90: { skyTop: 5, depths: [60_000] } });
		const village: Peak = { ...peakAt(90.5, 60_000, 'Ves'), kind: 'village' };
		const city: Peak = { ...peakAt(90.5, 60_000, 'Město'), kind: 'city', population: 500_000 };
		expect(projectPeak(meta, depth, village)).toBeNull();
		expect(projectPeak(meta, depth, city)).not.toBeNull();
	});

	it('a populous city outranks a nearer nondescript peak', () => {
		const depth = makeDepth({
			90: { skyTop: 5, depths: [20_000] },
			180: { skyTop: 7, depths: [60_000] }
		});
		const city: Peak = { ...peakAt(180.5, 60_000, 'Praha'), kind: 'city', population: 1_300_000 };
		const marks = projectPeaks(meta, depth, [peakAt(90.5, 20_000, 'Kopec'), city]);
		expect(marks.map((m) => m.name)).toEqual(['Praha', 'Kopec']);
		expect(marks[0].population).toBe(1_300_000);
	});
});

describe('layoutSkyLabels — slats rising from the sky above their summits', () => {
	const W = 800, H = 400;
	const mk = (cx: number, cy: number, w = 60, label = 'X') => ({ label, cx, cy, pillW: w });
	const R = Math.PI / 4;

	it('starts the slat just above the anchor, at the default 45°', () => {
		const [l] = layoutSkyLabels([mk(400, 200)], W, H);
		expect(l.ox).toBe(400);
		expect(l.oy).toBe(200 - 12); // cy - leader
		expect(l.angle).toBeCloseTo(R, 9);
		expect(l.pillH).toBe(20);
	});

	it('thins same-neighborhood labels: the higher-priority one wins its column', () => {
		const placed = layoutSkyLabels([mk(400, 200, 60, 'First'), mk(410, 205, 60, 'Second')], W, H);
		expect(placed.map((p) => p.label)).toEqual(['First']);
	});

	it('parallel slats tile at Δx·sin θ ≥ pillH + gap, whatever the label length', () => {
		// pitch 33 px > 23/sin45 = 32.5 → both fit, even with 300 px names
		const [a, b] = layoutSkyLabels([mk(400, 200, 300), mk(433, 200, 300)], W, H);
		expect(a.label).toBe('X');
		expect(b).toBeDefined();
		// pitch 30 px < 32.5 → the second is skipped
		expect(layoutSkyLabels([mk(400, 200, 300), mk(430, 200, 300)], W, H)).toHaveLength(1);
	});

	it('at 0° it is a horizontal, non-stacking layout: the next anchor must clear the previous label', () => {
		const opts = { angleDeg: 0 };
		expect(layoutSkyLabels([mk(400, 200, 60), mk(450, 200, 60)], W, H, opts)).toHaveLength(1);
		const [a, b] = layoutSkyLabels([mk(400, 200, 60), mk(464, 200, 60)], W, H, opts);
		expect(a.oy).toBe(b.oy); // no stacking: same height
		expect(a.angle).toBe(0);
	});

	it('a shorter slat lets a closer neighbour in once it ends before the neighbour starts', () => {
		// 30 px pitch is too close for a long left slat…
		expect(layoutSkyLabels([mk(400, 200, 300), mk(430, 200, 60)], W, H)).toHaveLength(1);
		// …but a 15 px left slat is over (15 + 3 gap ≤ 30·cos45 = 21.2 along the
		// axis) before the neighbour's origin arrives, so both fit
		expect(layoutSkyLabels([mk(400, 200, 15), mk(430, 200, 60)], W, H)).toHaveLength(2);
	});

	it('anchors at different heights: bands are compared perpendicular to the slats', () => {
		// same x pitch (26 px) but the right anchor sits 30 px higher: the
		// perpendicular separation 26·sin45 − 30·cos45 ≈ −2.8 → overlapping bands
		expect(layoutSkyLabels([mk(400, 200, 100), mk(426, 170, 100)], W, H)).toHaveLength(1);
		// …and 30 px LOWER: 26·sin45 + 30·cos45 ≈ 39.6 ≥ 23 → both fit
		expect(layoutSkyLabels([mk(400, 200, 100), mk(426, 230, 100)], W, H)).toHaveLength(2);
	});

	it('extra input fields ride through to the placed pills', () => {
		const [l] = layoutSkyLabels([{ ...mk(400, 200), cls: 'summit', mark: 7 }], W, H);
		expect(l.cls).toBe('summit');
		expect(l.mark).toBe(7);
	});

	it('hitSkyLabel inverse-rotates the tap into the pill frame, with touch slop', () => {
		const placed = layoutSkyLabels([mk(400, 200, 60, 'Hit')], W, H);
		const { ox, oy, pillW, pillH } = placed[0];
		// a point half-way along the axis and half a pill above it (in the frame)
		const along = pillW / 2, across = -pillH / 2;
		const px = ox + along * Math.cos(R) + across * Math.sin(R);
		const py = oy - along * Math.sin(R) + across * Math.cos(R);
		expect(hitSkyLabel(placed, px, py)?.label).toBe('Hit');
		// just outside the far end along the axis (beyond slop) → miss
		const fx = ox + (pillW + 20) * Math.cos(R);
		const fy = oy - (pillW + 20) * Math.sin(R);
		expect(hitSkyLabel(placed, fx, fy)).toBeNull();
		// slop: 3 px before the origin still hits
		expect(hitSkyLabel(placed, ox - 3 * Math.cos(R), oy + 3 * Math.sin(R))?.label).toBe('Hit');
	});

	it('drops a slat that would start above the canvas top; keeps one that merely runs off it', () => {
		expect(layoutSkyLabels([mk(400, 20)], W, H)).toHaveLength(0); // origin at y=8, top edge at 2 → 8-14 < 2
		const [l] = layoutSkyLabels([mk(400, 60, 300)], W, H); // 300 px slat rises 212 px above y=48
		expect(l).toBeDefined();
	});
});

describe('texToCanvas — screen mapping on the cylinder', () => {
	const W = 800, H = 400;

	it('maps within a plain rect', () => {
		const rect = { x1: 0.2, y1: 0, x2: 0.45, y2: (20 / 360) };
		const p = texToCanvas(meta, rect, 0.325, 0.5, W, H)!;
		expect(p.cx).toBeCloseTo(W / 2, 6);
	});

	it('wraps across the seam', () => {
		const rect = { x1: 0.9, y1: 0, x2: 1.1, y2: (20 / 360) };
		const p = texToCanvas(meta, rect, 0.05, 0.5, W, H)!; // u=0.05 ≡ x=1.05
		expect(p.cx).toBeCloseTo(0.75 * W, 6);
	});

	it('culls marks outside the viewport horizontally', () => {
		const rect = { x1: 0.2, y1: 0, x2: 0.45, y2: (20 / 360) };
		expect(texToCanvas(meta, rect, 0.7, 0.5, W, H)).toBeNull();
	});
});
