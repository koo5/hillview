import { describe, expect, it } from 'vitest';
import {
	angularSpanDeg,
	azimuthAtU,
	azimuthForColumn,
	clampPartialOffX,
	compassTicks,
	depthBlobHeader,
	destinationPoint,
	hexToRgb,
	isDepthBlob,
	normalizeRect,
	parseDepthBlob,
	pickFromDepth,
	pickFromDepthOrHorizon,
	rectFromView,
	type TerrainMeta,
	type ViewRect,
	viewFromRect,
	wedgeFromRect,
	wrap01
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

describe('pickFromDepthOrHorizon — sky clicks snap to the skyline', () => {
	const depth = new Uint16Array(meta.width * meta.height);
	const col = 1800;
	for (let row = 250; row < meta.height; row++) depth[row * meta.width + col] = 5000; // 20 km

	it('sky click snaps down to the first terrain row in the column', () => {
		const p = pickFromDepthOrHorizon(meta, depth, col, 10)!;
		expect(p.row).toBe(250);
		expect(p.distance_m).toBe(20000);
	});

	it('a terrain click is unchanged', () => {
		expect(pickFromDepthOrHorizon(meta, depth, col, 300)!.row).toBe(300);
	});

	it('an all-sky column still returns null', () => {
		expect(pickFromDepthOrHorizon(meta, depth, 0, 10)).toBeNull();
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

describe('clampPartialOffX — sectors clamp, full panos wrap', () => {
	const sector: TerrainMeta = { ...meta, width: 720, az_start: 351, az_end: 8.975 };
	// span = 0.05 × 720 = 36° → partial

	it('full 360° keeps cylinder wrap', () => {
		expect(clampPartialOffX(meta, 1.25, 2)).toBeCloseTo(0.25, 9);
	});

	it('a sector clamps panning to its edges', () => {
		expect(clampPartialOffX(sector, -0.2, 2)).toBe(0);
		expect(clampPartialOffX(sector, 0.9, 2)).toBeCloseTo(0.5, 9); // 1 - 1/scale
		expect(clampPartialOffX(sector, 0.3, 2)).toBeCloseTo(0.3, 9);
	});

	it('at fit zoom a sector pins to its start', () => {
		expect(clampPartialOffX(sector, 0.4, 1)).toBe(0);
	});
});

describe('compassTicks — azimuth ruler for the current view', () => {
	const a = meta.height / meta.width;

	it('full 360° view: 15° minors, cardinals at the right x positions', () => {
		const ticks = compassTicks(meta, { x1: 0, y1: 0, x2: 1, y2: a }, 720);
		// pxPerDeg = 2 → 1°/5° too dense, 15° (30 px) wins
		const azs = ticks.filter((t) => t.major).map((t) => t.label);
		expect(azs.slice(0, 4)).toEqual(['N', 'NE', 'E', 'SE']);
		const east = ticks.find((t) => t.azimuthDeg === 90 && t.major)!;
		expect(east.x).toBeCloseTo(180, 0); // 90° of 360° across 720 px
		expect(east.label).toBe('E');
	});

	it('zoomed view gets degree labels on 5° minors', () => {
		// 10% of the sweep = 36°, 720 px → 20 px/deg → 5° minors (100 px)
		const ticks = compassTicks(meta, { x1: 0.2, y1: 0, x2: 0.3, y2: a }, 720);
		const minor = ticks.find((t) => !t.major && t.label)!;
		expect(minor.label).toMatch(/°$/);
	});

	it('seam-straddling view wraps azimuths but keeps x monotonic', () => {
		const ticks = compassTicks(meta, { x1: 0.9, y1: 0, x2: 1.1, y2: a }, 720);
		const north = ticks.find((t) => t.label === 'N')!;
		expect(north.x).toBeGreaterThan(300); // due north mid-view
		expect(north.x).toBeLessThan(420);
		for (let i = 1; i < ticks.length; i++) expect(ticks[i].x).toBeGreaterThan(ticks[i - 1].x);
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

describe('parseDepthBlob — the HVD1 container', () => {
	it('reads the header, reserved bytes and all', () => {
		const buf = blob([1, 2, 3, 4], 2, 2);
		expect(depthBlobHeader(buf)).toEqual({ version: 1, headerBytes: 32, width: 2, height: 2, scaleM: 4 });
		expect(new Uint8Array(buf, 20, 12).every((b) => b === 0)).toBe(true); // reserved
		expect(depthBlobHeader(new Uint16Array([1, 2, 3, 4]).buffer)).toBeNull();
	});

	const blob = (values: number[], width = values.length, height = 1, opts: { version?: number; headerBytes?: number } = {}) => {
		const buf = new ArrayBuffer(32 + values.length * 2);
		const dv = new DataView(buf);
		for (const [i, c] of [...'HVD1'].entries()) dv.setUint8(i, c.charCodeAt(0));
		dv.setUint16(4, opts.version ?? 1, true);
		dv.setUint16(6, opts.headerBytes ?? 32, true);
		dv.setUint32(8, width, true);
		dv.setUint32(12, height, true);
		dv.setFloat32(16, 4, true);
		new Uint16Array(buf, 32).set(values);
		return buf;
	};

	it('returns the samples as a view, with no copy', () => {
		const buf = blob([0, 1234, 65535, 7], 2, 2);
		const d = parseDepthBlob(buf, { width: 2, height: 2 });
		expect(Array.from(d)).toEqual([0, 1234, 65535, 7]);
		expect(d.buffer).toBe(buf); // a view, not a copy
		expect(d.byteOffset).toBe(32);
	});

	it('names itself, so gzip can never be confused with samples', () => {
		// a bare buffer of these samples starts with 1f 8b 08 — the collision
		const bare = new Uint16Array([0x8b1f, 0x0008]).buffer;
		expect(new Uint8Array(bare)[0]).toBe(0x1f);
		expect(isDepthBlob(bare)).toBe(false);
		const wrapped = blob([0x8b1f, 0x0008], 2, 1);
		expect(isDepthBlob(wrapped)).toBe(true);
		expect(Array.from(parseDepthBlob(wrapped))).toEqual([0x8b1f, 0x0008]);
	});

	it('refuses a version it does not speak, and a header it cannot trust', () => {
		expect(() => parseDepthBlob(blob([1, 2], 2, 1, { version: 2 }))).toThrow(/version 2/);
		expect(() => parseDepthBlob(blob([1, 2], 2, 1, { headerBytes: 8 }))).toThrow(/claims 8/);
		expect(() => parseDepthBlob(blob([1, 2], 2, 1, { headerBytes: 9999 }))).toThrow(/claims 9999/);
	});

	it('catches a truncated payload and a grid that is not the overlay\'s', () => {
		const buf = blob([1, 2, 3, 4], 2, 2);
		expect(() => parseDepthBlob(buf.slice(0, 36))).toThrow(/carries 4/);
		expect(() => parseDepthBlob(buf, { width: 4, height: 1 })).toThrow(/is 2×2, the overlay describes 4×1/);
	});

	it('refuses a headerless buffer — there is no legacy form', () => {
		const bare = new Uint16Array([1, 2, 3, 4]).buffer;
		expect(() => parseDepthBlob(bare, { width: 2, height: 2 })).toThrow(/no HVD1 header/);
		expect(() => parseDepthBlob(bare)).toThrow(/no HVD1 header/);
	});
});
