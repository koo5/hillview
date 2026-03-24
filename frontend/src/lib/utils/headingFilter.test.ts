import {describe, it, expect, beforeEach} from 'vitest';
import {HeadingFilter} from './headingFilter';
import {destinationPoint} from '../geo';

/**
 * Helper: generate a GPS position at a given lat/lng/speed/time.
 */
function pos(lat: number, lng: number, speed: number, timestamp: number) {
	return {lat, lng, speed, timestamp};
}

/**
 * Helper: simulate driving in a straight line from a start point.
 * Returns an array of positions along the route.
 */
function driveStraight(
	startLat: number, startLng: number, bearing: number,
	speedMs: number, intervalMs: number, count: number
) {
	const positions = [];
	let lat = startLat, lng = startLng;
	for (let i = 0; i < count; i++) {
		const distKm = (speedMs * intervalMs / 1000) / 1000; // m/s * s → km
		const dest = destinationPoint(lat, lng, bearing, distKm);
		lat = dest.lat;
		lng = dest.lng;
		positions.push(pos(lat, lng, speedMs, i * intervalMs));
	}
	return positions;
}

describe('HeadingFilter', () => {
	let filter: HeadingFilter;

	beforeEach(() => {
		filter = new HeadingFilter();
	});

	describe('speed gating', () => {
		it('returns null for positions below minimum speed', () => {
			expect(filter.update(pos(50, 14, 0.5, 0))).toBeNull();
			expect(filter.update(pos(50, 14, 1.0, 1000))).toBeNull();
			expect(filter.update(pos(50, 14, 1.4, 2000))).toBeNull();
		});

		it('returns null for null speed', () => {
			expect(filter.update({lat: 50, lng: 14, speed: null, timestamp: 0})).toBeNull();
		});

		it('does not update reference position during low speed', () => {
			// Feed low-speed positions, then two high-speed ones far apart
			filter.update(pos(50.0, 14.0, 0.5, 0));
			filter.update(pos(50.001, 14.001, 0.5, 1000));

			// First high-speed position becomes reference
			expect(filter.update(pos(50.0, 14.0, 5, 2000))).toBeNull();
			// Second gives first heading — bearing from (50,14) to destination
			const positions = driveStraight(50.0, 14.0, 90, 10, 2000, 2);
			filter.reset();
			const r1 = filter.update(positions[0]);
			expect(r1).toBeNull(); // first position = reference
			const r2 = filter.update(positions[1]);
			expect(r2).toBeCloseTo(90, -1); // heading ≈ 90°
		});
	});

	describe('distance gating', () => {
		it('returns null when positions are too close together', () => {
			// Two positions very close (< 10m default)
			filter.update(pos(50.0, 14.0, 5, 0));
			expect(filter.update(pos(50.00001, 14.00001, 5, 1000))).toBeNull();
		});
	});

	describe('heading estimation', () => {
		it('returns null for first two positions (need reference + first measurement)', () => {
			const r1 = filter.update(pos(50.0, 14.0, 5, 0));
			expect(r1).toBeNull(); // first = reference
		});

		it('estimates heading for straight northbound drive', () => {
			const positions = driveStraight(50.0, 14.0, 0, 15, 1000, 5);
			let heading: number | null = null;
			for (const p of positions) {
				heading = filter.update(p) ?? heading;
			}
			expect(heading).not.toBeNull();
			// Should be approximately 0° (north)
			expect(heading!).toBeLessThan(5);
		});

		it('estimates heading for straight eastbound drive', () => {
			const positions = driveStraight(0.0, 14.0, 90, 15, 1000, 5);
			let heading: number | null = null;
			for (const p of positions) {
				heading = filter.update(p) ?? heading;
			}
			expect(heading).not.toBeNull();
			expect(heading!).toBeGreaterThan(85);
			expect(heading!).toBeLessThan(95);
		});

		it('estimates heading for southbound drive', () => {
			const positions = driveStraight(50.0, 14.0, 180, 15, 1000, 5);
			let heading: number | null = null;
			for (const p of positions) {
				heading = filter.update(p) ?? heading;
			}
			expect(heading).not.toBeNull();
			expect(heading!).toBeGreaterThan(175);
			expect(heading!).toBeLessThan(185);
		});

		it('heading is always in [0, 360)', () => {
			const bearings = [0, 45, 90, 135, 180, 225, 270, 315, 359];
			for (const b of bearings) {
				const f = new HeadingFilter();
				const positions = driveStraight(50.0, 14.0, b, 15, 1000, 5);
				for (const p of positions) {
					const h = f.update(p);
					if (h !== null) {
						expect(h).toBeGreaterThanOrEqual(0);
						expect(h).toBeLessThan(360);
					}
				}
			}
		});
	});

	describe('stop and resume (gap bridging)', () => {
		it('bridges a stop: heading after resume uses pre-stop reference', () => {
			// Drive east at 15 m/s
			const driving1 = driveStraight(50.0, 14.0, 90, 15, 1000, 5);
			let heading: number | null = null;
			for (const p of driving1) {
				heading = filter.update(p) ?? heading;
			}
			expect(heading).not.toBeNull();
			const headingBeforeStop = heading!;

			// Stop: several low-speed positions (should be ignored)
			const lastDriving = driving1[driving1.length - 1];
			for (let i = 0; i < 5; i++) {
				const t = lastDriving.timestamp + (i + 1) * 1000;
				filter.update(pos(lastDriving.lat, lastDriving.lng + 0.00001 * i, 0.5, t));
			}

			// Resume driving east from roughly the same spot
			const resumeTime = lastDriving.timestamp + 6000;
			const driving2 = driveStraight(lastDriving.lat, lastDriving.lng, 90, 15, 1000, 5);
			for (let i = 0; i < driving2.length; i++) {
				driving2[i].timestamp = resumeTime + i * 1000;
			}

			for (const p of driving2) {
				heading = filter.update(p) ?? heading;
			}

			// Heading should still be approximately east
			expect(heading!).toBeGreaterThan(80);
			expect(heading!).toBeLessThan(100);
		});

		it('detects direction change immediately after stop', () => {
			// Drive east
			const driving1 = driveStraight(50.0, 14.0, 90, 15, 1000, 5);
			for (const p of driving1) {
				filter.update(p);
			}

			// Stop
			const lastPos = driving1[driving1.length - 1];
			for (let i = 0; i < 10; i++) {
				filter.update(pos(lastPos.lat, lastPos.lng, 0.3, lastPos.timestamp + (i + 1) * 1000));
			}

			// Resume driving NORTH — first valid sample should give ~north
			const resumeTime = lastPos.timestamp + 11000;
			const driving2 = driveStraight(lastPos.lat, lastPos.lng, 0, 15, 1000, 3);
			for (let i = 0; i < driving2.length; i++) {
				driving2[i].timestamp = resumeTime + i * 1000;
			}

			let heading: number | null = null;
			for (const p of driving2) {
				heading = filter.update(p) ?? heading;
			}

			// Should be close to north — no smoothing to hold it toward east
			expect(heading!).toBeLessThan(15);
		});
	});

	describe('reset', () => {
		it('clears all state', () => {
			const positions = driveStraight(50.0, 14.0, 90, 15, 1000, 5);
			for (const p of positions) {
				filter.update(p);
			}

			filter.reset();

			// After reset, first position should return null (needs reference)
			expect(filter.update(pos(50.0, 14.0, 10, 0))).toBeNull();
		});
	});

	describe('custom options', () => {
		it('respects custom minSpeed', () => {
			const f = new HeadingFilter({minSpeed: 5});
			// 3 m/s is above default (1.5) but below custom (5)
			expect(f.update(pos(50.0, 14.0, 3, 0))).toBeNull();
		});

		it('respects custom minDistance', () => {
			const f = new HeadingFilter({minDistance: 50});
			f.update(pos(50.0, 14.0, 10, 0)); // reference
			// 30m apart — above default (10m) but below custom (50m)
			const dest = destinationPoint(50.0, 14.0, 90, 0.03);
			expect(f.update(pos(dest.lat, dest.lng, 10, 1000))).toBeNull();
		});
	});
});
