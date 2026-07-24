import { describe, expect, it } from 'vitest';
import {
	artifactVersion,
	isViewable,
	markerStateOf,
	nearestRenderWithin,
	progressOf,
	wedgeArcLatLngs,
	WEDGE_MAX_FOV_DEG,
	type TerrainRender
} from './terrainModel';
import { bearingBetween, distanceBetween } from './geo';

function render(over: Partial<TerrainRender>): TerrainRender {
	return {
		id: 'r1',
		photo_id: null,
		lat: 50.0,
		lon: 14.5,
		status: 'done',
		error: null,
		meta: null,
		has_depth: false,
		has_preview: false,
		enqueued_at: '2026-07-24T00:00:00Z',
		finished_at: null,
		...over
	};
}

describe('markerStateOf', () => {
	it('maps API statuses onto the four marker states from the design doc', () => {
		expect(markerStateOf({ status: 'queued' })).toBe('queued');
		expect(markerStateOf({ status: 'rendering' })).toBe('rendering');
		expect(markerStateOf({ status: 'done' })).toBe('done');
		expect(markerStateOf({ status: 'error' })).toBe('failed');
		expect(markerStateOf({ status: 'failed' })).toBe('failed');
	});

	it('treats unknown statuses as queued (in-progress is the safe default)', () => {
		expect(markerStateOf({ status: 'somethingnew' })).toBe('queued');
	});
});

describe('isViewable', () => {
	it('needs meta AND both artifacts — status alone does not gate viewing', () => {
		const meta = { width: 10, height: 2, az_start: 0, az_end: 359, elev_max_deg: 10,
			elev_min_deg: -5, lat: 50, lon: 14.5, depth_scale_m: 4 };
		expect(isViewable(render({ meta, has_depth: true, has_preview: true, status: 'rendering' }))).toBe(true);
		expect(isViewable(render({ meta, has_depth: true, has_preview: false }))).toBe(false);
		expect(isViewable(render({ meta: null, has_depth: true, has_preview: true }))).toBe(false);
	});
});

describe('nearestRenderWithin (the range circle keeps its job)', () => {
	const center = { lat: 50.0, lng: 14.5 };
	// ~1° lat ≈ 111 km; offsets chosen for unambiguous in/out at metre ranges
	const near = render({ id: 'near', lat: 50.001, lon: 14.5 }); // ≈ 111 m north
	const far = render({ id: 'far', lat: 50.01, lon: 14.5 }); // ≈ 1.11 km north

	it('selects the nearest render inside the range circle', () => {
		expect(nearestRenderWithin([far, near], center, 2000)?.id).toBe('near');
	});

	it('range is in metres: 500 m excludes the 1.1 km render', () => {
		expect(nearestRenderWithin([far], center, 500)).toBeNull();
		expect(nearestRenderWithin([far], center, 2000)?.id).toBe('far');
	});

	it('returns null with no renders in range', () => {
		expect(nearestRenderWithin([], center, 1e6)).toBeNull();
		expect(nearestRenderWithin([near], center, 50)).toBeNull();
	});
});

describe('wedgeArcLatLngs (derived wedge geometry, pane -> map one-way)', () => {
	const vp = { lat: 50.0, lon: 14.5 };

	it('builds a sector: viewpoint first, then samples+1 arc points at radius', () => {
		const pts = wedgeArcLatLngs(vp, 90, 60, 1300, 24)!;
		expect(pts).toHaveLength(26);
		expect(pts[0]).toEqual([vp.lat, vp.lon]);
		for (const [lat, lng] of pts.slice(1)) {
			expect(distanceBetween(vp.lat, vp.lon, lat, lng) * 1000).toBeCloseTo(1300, 0);
		}
	});

	it('spans azimuth ± fov/2, symmetric about the center azimuth', () => {
		const pts = wedgeArcLatLngs(vp, 90, 60, 1300, 24)!;
		const first = pts[1];
		const last = pts[pts.length - 1];
		expect(bearingBetween(vp.lat, vp.lon, first[0], first[1])).toBeCloseTo(60, 1);
		expect(bearingBetween(vp.lat, vp.lon, last[0], last[1])).toBeCloseTo(120, 1);
		const mid = pts[13]; // sample i = 12 of 24 — the arc center
		expect(bearingBetween(vp.lat, vp.lon, mid[0], mid[1])).toBeCloseTo(90, 1);
	});

	it('returns null at full-panorama FOV (a wedge would be a meaningless disc)', () => {
		expect(wedgeArcLatLngs(vp, 0, 360, 1300)).toBeNull();
		expect(wedgeArcLatLngs(vp, 0, WEDGE_MAX_FOV_DEG, 1300)).toBeNull();
		expect(wedgeArcLatLngs(vp, 0, WEDGE_MAX_FOV_DEG - 1, 1300)).not.toBeNull();
	});

	it('keeps a visible sliver when zoomed deep (FOV floor)', () => {
		const pts = wedgeArcLatLngs(vp, 180, 0.1, 1300, 8)!;
		const first = pts[1];
		const last = pts[pts.length - 1];
		expect(bearingBetween(vp.lat, vp.lon, first[0], first[1])).toBeCloseTo(179, 1);
		expect(bearingBetween(vp.lat, vp.lon, last[0], last[1])).toBeCloseTo(181, 1);
	});
});

describe('progressOf (progress ship-order step 1)', () => {
	const meta = { width: 10, height: 2, az_start: 0, az_end: 359, elev_max_deg: 10,
		elev_min_deg: -5, lat: 50, lon: 14.5, depth_scale_m: 4 };

	it('reads the worker ping riding in meta', () => {
		expect(progressOf(render({ status: 'rendering', meta: { progress_pct: 42 } }))).toBe(42);
	});

	it('null when absent or malformed', () => {
		expect(progressOf(render({ meta: null }))).toBeNull();
		expect(progressOf(render({ meta }))).toBeNull();
		expect(progressOf(render({ meta: { progress_pct: 'x' as unknown as number } }))).toBeNull();
	});

	it('a bare progress ping is not viewable meta', () => {
		expect(isViewable(render({ meta: { progress_pct: 42 }, has_depth: true, has_preview: true }))).toBe(false);
	});
});

describe('artifactVersion (cache key: new bytes only, never per poll)', () => {
	const grid = { width: 10, height: 2, az_start: 0, az_end: 359, elev_max_deg: 10,
		elev_min_deg: -5, lat: 50, lon: 14.5, depth_scale_m: 4 };

	it('finished renders key on finished_at', () => {
		expect(artifactVersion(render({ finished_at: '2026-07-24T10:00:00Z' })))
			.toBe('2026-07-24T10:00:00Z');
	});

	it('streaming partials key on the milestone artifact_version', () => {
		const r = render({ status: 'rendering',
			meta: { ...grid, progress_pct: 47, artifact_version: 33 } });
		expect(artifactVersion(r)).toBe('33');
	});

	it('a %-only ping between milestones does NOT change the key', () => {
		const at33 = render({ status: 'rendering',
			meta: { ...grid, progress_pct: 33, artifact_version: 33 } });
		const at47 = render({ status: 'rendering',
			meta: { ...grid, progress_pct: 47, artifact_version: 33 } });
		expect(artifactVersion(at47)).toBe(artifactVersion(at33));
	});

	it('falls back to a stable default before any artifacts', () => {
		expect(artifactVersion(render({ finished_at: null, meta: { progress_pct: 5 } }))).toBe('0');
	});
});
