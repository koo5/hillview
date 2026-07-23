import { describe, expect, it } from 'vitest';
import {
	azimuthForColumn,
	destinationPoint,
	hexToRgb,
	pickFromDepth,
	type TerrainMeta
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
