import { describe, expect, it } from 'vitest';
import type { TerrainMeta } from './depthPanoViewer';
import { destinationPoint } from './depthPanoViewer';
import {
	bearingDistance,
	colForAzimuth,
	hitSkyLabel,
	labelPriority,
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

describe('layoutSkyLabels — pills above summits, stacking upward', () => {
	const W = 800, H = 400;
	const mk = (cx: number, cy: number, w = 60, label = 'X') => ({ label, cx, cy, pillW: w });

	it('places the pill centered above the target, leader-gap clear of it', () => {
		const [l] = layoutSkyLabels([mk(400, 200)], W, H);
		expect(l.tx).toBe(400 - 30);
		expect(l.ty).toBe(200 - 12 - 20); // cy - leader - pillH
	});

	it('thins same-neighborhood labels: the higher-priority one wins its column', () => {
		const placed = layoutSkyLabels([mk(400, 200, 60, 'First'), mk(410, 205, 60, 'Second')], W, H);
		expect(placed.map((p) => p.label)).toEqual(['First']);
	});

	it('stacks pills whose columns are distinct but pills still overlap', () => {
		// 50 px apart: past minGapX (40), but 60 px pills overlap → stack
		const [a, b] = layoutSkyLabels([mk(400, 200), mk(450, 205)], W, H);
		expect(b.ty).toBe(a.ty - 20 - 3); // pillH + gap higher
	});

	it('non-overlapping labels keep their own height', () => {
		const [a, b] = layoutSkyLabels([mk(100, 200), mk(700, 200)], W, H);
		expect(a.ty).toBe(b.ty);
	});

	it('clamps pills horizontally into the canvas', () => {
		const [l] = layoutSkyLabels([mk(2, 200)], W, H);
		expect(l.tx).toBe(2);
	});

	it('hitSkyLabel finds the pill under a tap, with touch slop', () => {
		const placed = layoutSkyLabels([mk(400, 200, 60, 'Hit')], W, H);
		const { tx, ty, pillW, pillH } = placed[0];
		expect(hitSkyLabel(placed, tx + pillW / 2, ty + pillH / 2)?.label).toBe('Hit');
		expect(hitSkyLabel(placed, tx - 3, ty - 3)?.label).toBe('Hit'); // slop
		expect(hitSkyLabel(placed, tx + pillW + 20, ty)).toBeNull();
	});

	it('drops labels pushed past the top instead of piling up', () => {
		// distinct 45 px columns (past thinning) near the top edge: wide
		// pills overlap → stack upward → overflow the canvas top → dropped
		const crowd = Array.from({ length: 12 }, (_, i) => mk(150 + i * 45, 60, 200, `P${i}`));
		const placed = layoutSkyLabels(crowd, W, H);
		expect(placed.length).toBeLessThan(12);
		expect(placed.length).toBeGreaterThan(0);
		for (const l of placed) expect(l.ty).toBeGreaterThanOrEqual(2);
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
