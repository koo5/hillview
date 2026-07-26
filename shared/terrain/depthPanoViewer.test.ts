import { describe, expect, it } from 'vitest';
import {
	angularSpanDeg,
	azimuthAtU,
	azimuthForColumn,
	destinationPoint,
	hexToRgb,
	normalizeRect,
	pickFromDepth,
	rectFromView,
	viewFromRect,
	wedgeFromRect,
	wrap01,
	type TerrainMeta,
	type ViewRect
} from './depthPanoViewer';



const meta: TerrainMeta = {
	width: 7200,
	height: 400,
	az_start: 0.025,
	az_end: 359.975,
	az_step_deg: 0.05,
	elev_max_deg: 12,
	elev_min_deg: -8,
	lat: 50.0,
	lon: 14.5,
	depth_scale_m: 4
};

describe('destinationPoint', () => {
	it('moves 1000/R radians of latitude going north', () => {
		const p = destinationPoint(50, 14.5, 0, 1000);
		expect(p.lat).toBeCloseTo(50 + ((1000 / 6371000) * 180) / Math.PI, 8);
		expect(p.lon).toBeCloseTo(14.5, 6);
	});

	it('agrees with the renderer on an eastbound hop (values from renderer.py)', () => {
		// python: destination_point(50.0, 14.5, 90.0, 20_000.0)
		const p = destinationPoint(50, 14.5, 90, 20000);
		expect(p.lat).toBeCloseTo(49.999664, 4);
		expect(p.lon).toBeCloseTo(14.779818, 4);
	});

	it('wraps longitude across the antimeridian', () => {
		const p = destinationPoint(0, 179.9, 90, 50000);
		expect(p.lon).toBeLessThan(-179);
	});
});

describe('azimuthForColumn', () => {
	it('uses az_step_deg and wraps into [0, 360)', () => {
		expect(azimuthForColumn(meta, 0)).toBeCloseTo(0.025, 6);
		expect(azimuthForColumn(meta, 7199)).toBeCloseTo(359.975, 6);
	});

	it('derives the step from the span when az_step_deg is absent', () => {
		const m = { ...meta, az_step_deg: undefined };
		expect(azimuthForColumn(m, 3600)).toBeCloseTo(azimuthForColumn(meta, 3600), 6);
	});
});

describe('pickFromDepth', () => {
	const depth = new Uint16Array(meta.width * meta.height); // all sky
	const col = 1800; // az ≈ 90°
	const row = 200;
	depth[row * meta.width + col] = 5000; // 5000·4 m = 20 km

	it('returns null for sky and out-of-range pixels', () => {
		expect(pickFromDepth(meta, depth, 0, 0)).toBeNull();
		expect(pickFromDepth(meta, depth, -1, 5)).toBeNull();
		expect(pickFromDepth(meta, depth, meta.width, 5)).toBeNull();
	});

	it('recovers distance, azimuth, and geo coords for a terrain pixel', () => {
		const p = pickFromDepth(meta, depth, col, row)!;
		expect(p.distance_m).toBe(20000);
		expect(p.azimuth_deg).toBeCloseTo(90.025, 3);
		const q = destinationPoint(meta.lat, meta.lon, p.azimuth_deg, 20000);
		expect(p.lat).toBeCloseTo(q.lat, 8);
		expect(p.lon).toBeCloseTo(q.lon, 8);
	});
});

describe('hexToRgb', () => {
	it('parses with and without the hash', () => {
		expect(hexToRgb('#ff0080')[0]).toBeCloseTo(1);
		expect(hexToRgb('ff0080')[2]).toBeCloseTo(128 / 255, 2);
	});
});

describe('viewport rect (zoom view convention, width normalized to 1)', () => {
	const a = meta.height / meta.width; // 400/7200 = 1/18

	it('rectFromView at the reset view spans the full width', () => {
		const r = rectFromView(meta, { offX: 0, offY: 0, scale: 1 });
		expect(r).toEqual({ x1: 0, y1: 0, x2: 1, y2: a });
	});

	it('round-trips view -> rect -> view', () => {
		const v = { offX: 0.3, offY: 0.25, scale: 4 };
		const r = rectFromView(meta, v);
		expect(r.x2 - r.x1).toBeCloseTo(0.25, 9);
		expect(r.y2 - r.y1).toBeCloseTo(0.25 * a, 9);
		const back = viewFromRect(meta, r);
		expect(back.offX).toBeCloseTo(v.offX, 9);
		expect(back.offY).toBeCloseTo(v.offY, 9);
		expect(back.scale).toBeCloseTo(v.scale, 9);
	});

	it('viewFromRect wraps x onto the cylinder and clamps scale to [1, 40]', () => {
		expect(viewFromRect(meta, { x1: 1.9, y1: 0, x2: 2.4, y2: a / 2 }).offX).toBeCloseTo(0.9, 9);
		expect(viewFromRect(meta, { x1: -0.25, y1: 0, x2: 0.25, y2: a / 2 }).offX).toBeCloseTo(0.75, 9);
		expect(viewFromRect(meta, { x1: 0, y1: 0, x2: 4, y2: a }).scale).toBe(1);
		expect(viewFromRect(meta, { x1: 0, y1: 0, x2: 0.001, y2: a }).scale).toBe(40);
	});

	it('normalizeRect shifts seam-straddling x into [0, 1) preserving width', () => {
		const r: ViewRect = { x1: 1.3, y1: 0.01, x2: 1.55, y2: 0.02 };
		const n = normalizeRect(r);
		expect(n.x1).toBeCloseTo(0.3, 9);
		expect(n.x2).toBeCloseTo(0.55, 9);
		expect(n.y1).toBe(r.y1);
		const neg = normalizeRect({ x1: -0.2, y1: 0, x2: 0.05, y2: 0.01 });
		expect(neg.x1).toBeCloseTo(0.8, 9);
		expect(neg.x2).toBeCloseTo(1.05, 9);
		expect(normalizeRect({ x1: 0.4, y1: 0, x2: 0.6, y2: 0.01 }).x1).toBe(0.4);
	});

	it('wrap01 maps onto [0, 1)', () => {
		expect(wrap01(1.25)).toBeCloseTo(0.25, 9);
		expect(wrap01(-0.25)).toBeCloseTo(0.75, 9);
		expect(wrap01(1)).toBe(0);
	});
});

describe('derived wedge (rect -> map, one-way)', () => {
	it('covers the full sweep for a full-width panorama', () => {
		expect(angularSpanDeg(meta)).toBeCloseTo(360, 6);
	});

	it('azimuthAtU inverts the column-center mapping', () => {
		// u at the CENTER of column c is (c + 0.5)/width
		expect(azimuthAtU(meta, 0.5 / meta.width)).toBeCloseTo(azimuthForColumn(meta, 0), 9);
		expect(azimuthAtU(meta, 0.5)).toBeCloseTo(180.0, 6);
	});

	it('center-x -> azimuth, width -> FOV', () => {
		const w = wedgeFromRect(meta, { x1: 0.25, y1: 0, x2: 0.75, y2: 0.02 });
		expect(w.azimuthDeg).toBeCloseTo(180.0, 6);
		expect(w.fovDeg).toBeCloseTo(180.0, 6);
	});

	it('handles a seam-straddling rect (x beyond 1 before normalization)', () => {
		const w = wedgeFromRect(meta, { x1: 0.9, y1: 0, x2: 1.1, y2: 0.01 });
		expect(w.azimuthDeg).toBeCloseTo(0.0, 6); // due north, across the seam
		expect(w.fovDeg).toBeCloseTo(72.0, 6);
	});

	it('caps FOV at the full sweep', () => {
		const w = wedgeFromRect(meta, { x1: -0.5, y1: 0, x2: 1.5, y2: 0.05 });
		expect(w.fovDeg).toBeCloseTo(360, 6);
	});
});
