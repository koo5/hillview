import { describe, expect, it } from 'vitest';
import {
	isViewable,
	markerStateOf,
	nearestRenderWithin,
	type TerrainRender
} from './terrainModel';

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
