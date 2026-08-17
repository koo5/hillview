import { describe, expect, it } from 'vitest';
import {
	createOverlayProjector,
	effectiveFit,
	hstepAt,
	pickFromOverlay,
	resampleSteps,
	resampleWarp,
	skylineFromDepth,
	skylinePolylines,
	warpAt,
	wrapDelta,
	type OverlayFit,
	type OverlaySkyline,
	type SkylineGrid,
	type TerrainOverlay
} from './overlayFit';

const baseFit: OverlayFit = {
	projection: 'equirect',
	centre_bearing: 180,
	fov_deg: 90,
	horizon_pct: 50,
	v_scale: 1,
	roll_deg: 0,
	warp: [0, 0],
	visibility_km: null
};

describe('wrapDelta', () => {
	it('wraps into (-180, 180]', () => {
		expect(wrapDelta(0)).toBe(0);
		expect(wrapDelta(370)).toBeCloseTo(10);
		expect(wrapDelta(-370)).toBeCloseTo(-10);
		// 350° and -10° are the same direction — the short way round
		expect(wrapDelta(350)).toBeCloseTo(-10);
	});
});

describe('warpAt', () => {
	it('interpolates linearly between handles', () => {
		expect(warpAt([0, 2], 0)).toBe(0);
		expect(warpAt([0, 2], 0.5)).toBeCloseTo(1);
		expect(warpAt([0, 2], 1)).toBeCloseTo(2);
	});

	it('clamps outside 0..1 instead of extrapolating', () => {
		expect(warpAt([0, 2], -1)).toBe(0);
		expect(warpAt([0, 2], 5)).toBe(2);
	});

	it('picks the right segment with more handles', () => {
		// handles at 0, 0.5, 1
		expect(warpAt([0, 4, 0], 0.25)).toBeCloseTo(2);
		expect(warpAt([0, 4, 0], 0.75)).toBeCloseTo(2);
	});
});

describe('resampleWarp', () => {
	it('is identity for the same count', () => {
		expect(resampleWarp([1, 2, 3], 3)).toEqual([1, 2, 3]);
	});

	it('preserves the shape when upsampling', () => {
		const up = resampleWarp([0, 2], 3);
		expect(up).toHaveLength(3);
		expect(up[0]).toBeCloseTo(0);
		expect(up[1]).toBeCloseTo(1);
		expect(up[2]).toBeCloseTo(2);
	});

	it('keeps the edges when downsampling', () => {
		const down = resampleWarp([0, 5, 9], 2);
		expect(down[0]).toBeCloseTo(0);
		expect(down[1]).toBeCloseTo(9);
	});

	it('clamps the count to 2..9', () => {
		expect(resampleWarp([0, 1], 1)).toHaveLength(2);
		expect(resampleWarp([0, 1], 50)).toHaveLength(9);
	});
});

describe('createOverlayProjector', () => {
	it('puts the centre bearing at the image centre, on the horizon', () => {
		const p = createOverlayProjector(baseFit, 1000, 400);
		const pt = p.projectAzimuth(180, 0)!;
		expect(pt.x).toBeCloseTo(500);
		expect(pt.y).toBeCloseTo(200);
	});

	it('scales linearly with the box, so any unit space agrees', () => {
		const small = createOverlayProjector(baseFit, 1000, 400);
		const big = createOverlayProjector(baseFit, 4000, 1600);
		const a = small.projectAzimuth(200, 3)!;
		const b = big.projectAzimuth(200, 3)!;
		expect(b.x).toBeCloseTo(a.x * 4);
		expect(b.y).toBeCloseTo(a.y * 4);
	});

	it('maps elevation upward at W/fov px per degree (equirect)', () => {
		const p = createOverlayProjector(baseFit, 900, 400);
		expect(p.pxPerDeg).toBeCloseTo(10); // 900 / 90
		const up = p.projectAzimuth(180, 5)!;
		expect(up.y).toBeCloseTo(200 - 50);
	});

	it('drops directions outside the frame', () => {
		const p = createOverlayProjector(baseFit, 1000, 400);
		expect(p.projectAzimuth(180 + 60, 0)).toBeNull();
		expect(p.projectAzimuth(180 - 60, 0)).toBeNull();
	});

	it('honours horizon_pct and v_scale', () => {
		const p = createOverlayProjector(
			{ ...baseFit, horizon_pct: 25, v_scale: 2 },
			900,
			400
		);
		expect(p.horizonY(450)).toBeCloseTo(100);
		expect(p.pxPerDeg).toBeCloseTo(20);
	});

	it('applies roll as a shear about the image centre', () => {
		const p = createOverlayProjector({ ...baseFit, roll_deg: 45 }, 1000, 400);
		expect(p.horizonY(500)).toBeCloseTo(200); // pivot unmoved
		expect(p.horizonY(600)).toBeCloseTo(300); // tan(45°) = 1
		expect(p.horizonY(400)).toBeCloseTo(100);
	});

	it('lifts the horizon by warp × pxPerDeg (warp is in degrees)', () => {
		// 900 px / 90° = 10 px per degree; a 2° warp lifts 20 px
		const p = createOverlayProjector({ ...baseFit, warp: [2, 2] }, 900, 400);
		expect(p.horizonY(0)).toBeCloseTo(200 - 20);
		expect(p.horizonY(900)).toBeCloseTo(200 - 20);
	});

	it('rectilinear pins to equirect at the centre and the frame edge', () => {
		// fRectH = (W/2)/tan(fov/2), so delta = ±fov/2 lands exactly on the
		// edge for both projections — which is why switching projection keeps
		// a rough fit instead of throwing it away
		const eq = createOverlayProjector(baseFit, 1000, 400);
		const rect = createOverlayProjector({ ...baseFit, projection: 'rectilinear' }, 1000, 400);
		expect(rect.projectAzimuth(180, 0)!.x).toBeCloseTo(eq.projectAzimuth(180, 0)!.x);
		expect(rect.projectAzimuth(180 + 45, 0)!.x).toBeCloseTo(1000);
		expect(eq.projectAzimuth(180 + 45, 0)!.x).toBeCloseTo(1000);
	});

	it('rectilinear compresses directions between centre and edge', () => {
		// tan is convex, so it runs below the equirect chord in between:
		// a rectilinear pano puts mid-frame terrain nearer the centre
		const eq = createOverlayProjector(baseFit, 1000, 400);
		const rect = createOverlayProjector({ ...baseFit, projection: 'rectilinear' }, 1000, 400);
		expect(rect.projectAzimuth(180 + 40, 0)!.x).toBeLessThan(
			eq.projectAzimuth(180 + 40, 0)!.x
		);
	});

	it('cylindrical matches equirect at the horizon and diverges above it', () => {
		const eq = createOverlayProjector(baseFit, 1000, 400);
		const cyl = createOverlayProjector({ ...baseFit, projection: 'cylindrical' }, 1000, 400);
		expect(cyl.projectAzimuth(200, 0)!.y).toBeCloseTo(eq.projectAzimuth(200, 0)!.y);
		// tan(e) > e, so a cylindrical pano puts high terrain higher
		expect(cyl.projectAzimuth(200, 20)!.y).toBeLessThan(eq.projectAzimuth(200, 20)!.y);
	});
});

// 4 columns × 6 rows spanning +6..-6° (2° per row), 10 m quanta
const grid: SkylineGrid = {
	width: 4,
	height: 6,
	elev_max_deg: 6,
	elev_min_deg: -6,
	depth_scale_m: 10
};

/** column c gets `depths` (metres) from row skyTop downward; 0 = sky */
function depthBuf(cols: Record<number, { skyTop: number; depths: number[] }>): Uint16Array {
	const d = new Uint16Array(grid.width * grid.height);
	for (const [cs, prof] of Object.entries(cols)) {
		const c = Number(cs);
		for (let r = prof.skyTop; r < grid.height; r++) {
			const m = prof.depths[Math.min(r - prof.skyTop, prof.depths.length - 1)];
			d[r * grid.width + c] = Math.round(m / grid.depth_scale_m);
		}
	}
	return d;
}

describe('skylineFromDepth', () => {
	it('returns the row-centre elevation of the topmost terrain pixel', () => {
		// column 1: terrain from row 2 down — row 2 centre is 6 - 2.5*2 = 1°
		const sky = skylineFromDepth(grid, depthBuf({ 1: { skyTop: 2, depths: [5000] } }), null);
		expect(sky[1]).toBeCloseTo(1);
	});

	it('leaves all-sky columns null', () => {
		const sky = skylineFromDepth(grid, depthBuf({ 1: { skyTop: 2, depths: [5000] } }), null);
		expect(sky[0]).toBeNull();
		expect(sky[2]).toBeNull();
	});

	it('cuts to the first row within the visibility cutoff', () => {
		// far ridge at rows 1-2 (50 km), near ridge from row 4 (5 km)
		const d = depthBuf({ 0: { skyTop: 1, depths: [50000, 50000, 50000, 5000] } });
		const full = skylineFromDepth(grid, d, null);
		const fogged = skylineFromDepth(grid, d, 10000);
		expect(full[0]).toBeCloseTo(6 - 1.5 * 2); // row 1 → 3°
		expect(fogged[0]).toBeCloseTo(6 - 4.5 * 2); // row 4 → -3°
		expect(fogged[0]!).toBeLessThan(full[0]!);
	});

	it('returns null when everything visible is beyond the cutoff', () => {
		const d = depthBuf({ 0: { skyTop: 1, depths: [50000] } });
		expect(skylineFromDepth(grid, d, 10000)[0]).toBeNull();
	});
});

describe('skylinePolylines', () => {
	const skyline: OverlaySkyline = {
		az_start: 170,
		az_step: 1,
		elev_deg: [1, 2, null, 3, 4]
	};

	it('breaks the curve at gaps instead of bridging them', () => {
		const proj = createOverlayProjector(baseFit, 1000, 400);
		const runs = skylinePolylines(skyline, proj, baseFit);
		expect(runs).toHaveLength(2);
		expect(runs[0]).toHaveLength(2);
		expect(runs[1]).toHaveLength(2);
	});

	it('places samples left-to-right by azimuth', () => {
		const proj = createOverlayProjector(baseFit, 1000, 400);
		const runs = skylinePolylines(skyline, proj, baseFit);
		expect(runs[0][0].x).toBeLessThan(runs[0][1].x);
		expect(runs[1][0].x).toBeGreaterThan(runs[0][1].x);
	});

	it('treats an empty skyline as nothing to draw, not a crash', () => {
		// this runs inside the viewer's per-frame paint
		const proj = createOverlayProjector(baseFit, 1000, 400);
		expect(skylinePolylines({ az_start: 0, az_step: 1, elev_deg: [] }, proj, baseFit)).toEqual(
			[]
		);
		expect(
			skylinePolylines({ az_start: 0, az_step: 1 } as OverlaySkyline, proj, baseFit)
		).toEqual([]);
	});

	it('drops runs that fall outside the frame', () => {
		// same skyline, a photo pointed 70° away from it
		const elsewhere = { ...baseFit, centre_bearing: 250, fov_deg: 10 };
		const proj = createOverlayProjector(elsewhere, 1000, 400);
		expect(skylinePolylines(skyline, proj, elsewhere)).toHaveLength(0);
	});
});

describe('unproject', () => {
	// the click-back is only as good as this inverse: a 1° error puts a
	// "click a mountain" answer on the wrong mountain
	const cases: OverlayFit['projection'][] = ['equirect', 'cylindrical', 'rectilinear'];

	for (const projection of cases) {
		it(`round-trips project() for ${projection}`, () => {
			const fit = { ...baseFit, projection, warp: [0.5, -0.3], roll_deg: 2 };
			const p = createOverlayProjector(fit, 1600, 900);
			for (const az of [160, 175, 180, 190, 205]) {
				for (const elev of [-3, 0, 2.5, 7]) {
					const pt = p.projectAzimuth(az, elev);
					if (!pt) continue;
					const ray = p.unproject(pt.x, pt.y);
					expect(ray.azimuth_deg).toBeCloseTo(az, 6);
					expect(ray.elev_deg).toBeCloseTo(elev, 6);
				}
			}
		});
	}

	for (const projection of cases) {
		it(`round-trips project() under segment shifts for ${projection}`, () => {
			// a stitched pano: three panels, the middle one shifted 0.4° left
			// and the right one 0.25° right of the ideal projection — the
			// click-back must still land on the azimuth a point was projected
			// from (points that fall into a seam gap simply do not project)
			const fit = { ...baseFit, projection, warp: [0.5, 0, -0.3, 0], hwarp: [0, 0.4, -0.25, 0], roll_deg: 1 };
			const p = createOverlayProjector(fit, 1600, 900);
			let seen = 0;
			for (const az of [150, 160, 175, 180, 190, 205, 215]) {
				for (const elev of [-3, 0, 2.5, 7]) {
					const pt = p.projectAzimuth(az, elev);
					if (!pt) continue;
					seen++;
					const ray = p.unproject(pt.x, pt.y);
					expect(ray.azimuth_deg).toBeCloseTo(az, 6);
					expect(ray.elev_deg).toBeCloseTo(elev, 6);
				}
			}
			expect(seen).toBeGreaterThan(20);
		});
	}

	it('segment shifts are rigid steps: a whole panel moves, nothing stretches', () => {
		// two segments (3 handles): the right half shifted +0.5° (its content
		// sits 0.5° left of ideal); the left half untouched
		const p0 = createOverlayProjector(baseFit, 1800, 900); // 90° → 20 px/°
		const p1 = createOverlayProjector({ ...baseFit, hwarp: [0, 0.5, 0] }, 1800, 900);
		for (const az of [200, 210, 220]) // right half, well clear of the seam
			expect(p1.projectAzimuth(az, 0)!.x).toBeCloseTo(p0.projectAzimuth(az, 0)!.x - 10, 6);
		for (const az of [140, 150, 170]) // left half: identical
			expect(p1.projectAzimuth(az, 0)!.x).toBeCloseTo(p0.projectAzimuth(az, 0)!.x, 9);
		// an azimuth that now falls into the seam gap is not shown at all: the
		// right panel starts at ideal 180°+0.5°, the left one ends at 180°
		expect(p1.projectAzimuth(180.2, 0)).toBeNull();
		// an all-zero hwarp is exactly no shift
		const pz = createOverlayProjector({ ...baseFit, hwarp: [0, 0, 0] }, 1800, 900);
		expect(pz.projectAzimuth(150, 2)!.x).toBeCloseTo(p0.projectAzimuth(150, 2)!.x, 9);
	});

	it('hstepAt / resampleSteps keep steps as steps', () => {
		expect(hstepAt([0, 0.5, 0], 0.25)).toBe(0);
		expect(hstepAt([0, 0.5, 0], 0.75)).toBe(0.5);
		expect(hstepAt([0, 0.5, 0], 1)).toBe(0.5); // clamps into the last segment
		// 2 segments → 4 segments: each new segment takes the old segment its midpoint is in
		expect(resampleSteps([0, 0.5, 0], 5)).toEqual([0, 0, 0.5, 0.5, 0]);
		// 4 → 2 keeps the value at each new midpoint
		expect(resampleSteps([0.1, 0.2, 0.3, 0.4, 0], 3)).toEqual([0.2, 0.4, 0]); // midpoints 0.25 / 0.75 fall in old segments 1 / 3
	});

	it('a pano over 360° (closing overlap) still projects and round-trips', () => {
		for (const projection of ['equirect', 'cylindrical'] as const) {
			const fit = { ...baseFit, projection, fov_deg: 365, centre_bearing: 0 };
			const p = createOverlayProjector(fit, 3650, 400); // 10 px/°
			// content 182° right of centre also appears 178° LEFT of it; the
			// projector draws the copy nearer the centre — the left one
			expect(p.projectAzimuth(182, 0)!.x).toBeCloseTo(3650 * (0.5 - 178 / 365), 6);
			// the duplicated strip at the right edge unprojects to the right azimuth
			expect(p.unproject(3650 * (0.5 + 181 / 365), 200).azimuth_deg).toBeCloseTo(181, 6);
			for (const az of [10, 90, 179, 200, 350])
				for (const elev of [-2, 0, 3]) {
					const pt = p.projectAzimuth(az, elev);
					if (!pt) continue;
					const ray = p.unproject(pt.x, pt.y);
					expect(ray.azimuth_deg).toBeCloseTo(az, 6);
					expect(ray.elev_deg).toBeCloseTo(elev, 6);
				}
		}
	});

	it('reads the horizon line as elevation zero', () => {
		const fit = { ...baseFit, warp: [1, -1], roll_deg: 3 };
		const p = createOverlayProjector(fit, 1600, 900);
		for (const x of [0, 400, 800, 1200, 1600]) {
			expect(p.unproject(x, p.horizonY(x)).elev_deg).toBeCloseTo(0, 9);
		}
	});

	it('normalizes azimuth into [0, 360)', () => {
		const p = createOverlayProjector({ ...baseFit, centre_bearing: 5 }, 1000, 400);
		const ray = p.unproject(0, 200); // far left of a 90° frame → 5 - 45 = -40
		expect(ray.azimuth_deg).toBeCloseTo(320);
	});
});

describe('pickFromOverlay', () => {
	// 8 columns spanning azimuths 176.5..183.5, 6 rows over +6..-6°
	const depthRef = {
		url: 'https://pics.example/terrain/abc.depth.bin.gz',
		width: 8,
		height: 6,
		az_start: 176.5,
		az_end: 183.5,
		az_step_deg: 1,
		elev_max_deg: 6,
		elev_min_deg: -6,
		lat: 50,
		lon: 14.5,
		depth_scale_m: 10,
		max_distance_m: 100_000
	};

	function overlayWith(depth?: typeof depthRef): TerrainOverlay {
		return {
			version: 1,
			fit: baseFit,
			skyline: { az_start: 176.5, az_step: 1, elev_deg: [] },
			labels: [],
			render: { id: 'r1', lat: 50, lon: 14.5 },
			attribution: 'test',
			...(depth ? { depth } : {})
		};
	}

	/** terrain from `skyTop` down, at a constant distance */
	function buf(col: number, skyTop: number, distanceM: number): Uint16Array {
		const d = new Uint16Array(depthRef.width * depthRef.height);
		for (let r = skyTop; r < depthRef.height; r++) {
			d[r * depthRef.width + col] = distanceM / depthRef.depth_scale_m;
		}
		return d;
	}

	it('turns a pixel into real coordinates', () => {
		const overlay = overlayWith(depthRef);
		const proj = createOverlayProjector(baseFit, 1000, 400);
		// column 4 is azimuth 180.5; put terrain there at 12 km, from row 2 (1°)
		const pt = proj.projectAzimuth(180.5, 0.5)!;
		const pick = pickFromOverlay(overlay, buf(4, 2, 12000), pt.x, pt.y, 1000, 400);
		expect(pick).not.toBeNull();
		expect(pick!.distance_m).toBe(12000);
		expect(pick!.azimuth_deg).toBeCloseTo(180.5);
		// 12 km roughly due south of the viewpoint
		expect(pick!.lat).toBeLessThan(50);
		expect(Math.abs(pick!.lon - 14.5)).toBeLessThan(0.05);
	});

	it('snaps a sky click down to the horizon in that direction', () => {
		const overlay = overlayWith(depthRef);
		const proj = createOverlayProjector(baseFit, 1000, 400);
		const high = proj.projectAzimuth(180.5, 5.5)!; // above the ridge
		const pick = pickFromOverlay(overlay, buf(4, 3, 8000), high.x, high.y, 1000, 400);
		expect(pick?.distance_m).toBe(8000);
	});

	it('returns null for a direction the render never covered', () => {
		const overlay = overlayWith(depthRef);
		const proj = createOverlayProjector(baseFit, 1000, 400);
		const off = proj.projectAzimuth(200, 0)!; // outside the 7° sector
		expect(pickFromOverlay(overlay, buf(4, 2, 12000), off.x, off.y, 1000, 400)).toBeNull();
	});

	it('returns null for an all-sky column', () => {
		const overlay = overlayWith(depthRef);
		const proj = createOverlayProjector(baseFit, 1000, 400);
		const pt = proj.projectAzimuth(178.5, 0)!;
		expect(pickFromOverlay(overlay, buf(4, 2, 12000), pt.x, pt.y, 1000, 400)).toBeNull();
	});

	it('returns null when the overlay graduated without a depth buffer', () => {
		expect(pickFromOverlay(overlayWith(), new Uint16Array(48), 500, 200, 1000, 400)).toBeNull();
	});

	it('follows a local horizon adjustment, in the right direction', () => {
		// horizon_pct is measured DOWN the image, so a bigger pct puts the
		// horizon lower and makes a fixed pixel read as HIGHER above it — i.e.
		// an earlier (smaller) row of the render grid
		const depth = buf(4, 0, 9000);
		const plain = createOverlayProjector(baseFit, 1000, 400);
		const pt = plain.projectAzimuth(180.5, 0.5)!;
		const base = pickFromOverlay(overlayWith(depthRef), depth, pt.x, pt.y, 1000, 400);
		const lowerHorizon = pickFromOverlay(
			{ ...overlayWith(depthRef), user_adjust: { horizon_pct_delta: 5 } },
			depth, pt.x, pt.y, 1000, 400
		);
		const higherHorizon = pickFromOverlay(
			{ ...overlayWith(depthRef), user_adjust: { horizon_pct_delta: -5 } },
			depth, pt.x, pt.y, 1000, 400
		);
		expect(base!.row).toBe(2);
		expect(lowerHorizon!.row).toBeLessThan(base!.row);
		expect(higherHorizon!.row).toBeGreaterThan(base!.row);
	});
});

describe('effectiveFit', () => {
	const overlay: TerrainOverlay = {
		version: 1,
		fit: baseFit,
		skyline: { az_start: 0, az_step: 1, elev_deg: [] },
		labels: [],
		render: { id: 'r1', lat: 50, lon: 14.5 },
		attribution: 'test'
	};

	it('returns the graduated fit untouched when nothing is adjusted', () => {
		expect(effectiveFit(overlay)).toBe(overlay.fit);
	});

	it('applies a local horizon nudge without mutating the graduated fit', () => {
		const adjusted = effectiveFit({ ...overlay, user_adjust: { horizon_pct_delta: -3 } });
		expect(adjusted.horizon_pct).toBeCloseTo(47);
		expect(overlay.fit.horizon_pct).toBe(50);
	});
});
