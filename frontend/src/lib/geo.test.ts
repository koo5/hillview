import { describe, it, expect } from 'vitest';
import { destinationPoint, bearingBetween, distanceBetween } from './geo';

describe('geo utilities', () => {
	describe('distanceBetween', () => {
		it('returns 0 for identical points', () => {
			expect(distanceBetween(50.0, 14.0, 50.0, 14.0)).toBe(0);
		});

		it('calculates known distance: Prague to Brno (~185 km)', () => {
			// Prague: 50.0755, 14.4378  Brno: 49.1951, 16.6068
			const d = distanceBetween(50.0755, 14.4378, 49.1951, 16.6068);
			expect(d).toBeGreaterThan(180);
			expect(d).toBeLessThan(190);
		});

		it('calculates pole-to-pole distance (~20015 km)', () => {
			const d = distanceBetween(90, 0, -90, 0);
			expect(d).toBeGreaterThan(20000);
			expect(d).toBeLessThan(20030);
		});

		it('calculates quarter-equator distance (~10008 km)', () => {
			const d = distanceBetween(0, 0, 0, 90);
			expect(d).toBeGreaterThan(10000);
			expect(d).toBeLessThan(10020);
		});

		it('is symmetric', () => {
			const d1 = distanceBetween(50.0, 14.0, 48.0, 16.0);
			const d2 = distanceBetween(48.0, 16.0, 50.0, 14.0);
			expect(d1).toBeCloseTo(d2, 10);
		});

		it('handles crossing the antimeridian', () => {
			const d = distanceBetween(0, 179, 0, -179);
			// Should be ~222 km (2 degrees at equator)
			expect(d).toBeGreaterThan(220);
			expect(d).toBeLessThan(224);
		});
	});

	describe('bearingBetween', () => {
		it('returns 0 for due north', () => {
			const b = bearingBetween(50.0, 14.0, 51.0, 14.0);
			expect(b).toBeCloseTo(0, 0);
		});

		it('returns ~90 for due east (near equator)', () => {
			const b = bearingBetween(0, 14.0, 0, 15.0);
			expect(b).toBeCloseTo(90, 0);
		});

		it('returns 180 for due south', () => {
			const b = bearingBetween(51.0, 14.0, 50.0, 14.0);
			expect(b).toBeCloseTo(180, 0);
		});

		it('returns ~270 for due west (near equator)', () => {
			const b = bearingBetween(0, 15.0, 0, 14.0);
			expect(b).toBeCloseTo(270, 0);
		});

		it('result is always in [0, 360)', () => {
			const bearings = [
				bearingBetween(50, 14, 51, 15),
				bearingBetween(50, 14, 49, 13),
				bearingBetween(50, 14, 49, 15),
				bearingBetween(50, 14, 51, 13),
			];
			for (const b of bearings) {
				expect(b).toBeGreaterThanOrEqual(0);
				expect(b).toBeLessThan(360);
			}
		});

		it('handles northeast diagonal', () => {
			// Prague heading northeast
			const b = bearingBetween(50.0, 14.0, 51.0, 15.0);
			expect(b).toBeGreaterThan(20);
			expect(b).toBeLessThan(50);
		});
	});

	describe('destinationPoint', () => {
		it('returns same point for 0 distance', () => {
			const p = destinationPoint(50.0, 14.0, 90, 0);
			expect(p.lat).toBeCloseTo(50.0, 6);
			expect(p.lng).toBeCloseTo(14.0, 6);
		});

		it('moves north correctly', () => {
			// 111.195 km ≈ 1 degree of latitude
			const p = destinationPoint(50.0, 14.0, 0, 111.195);
			expect(p.lat).toBeCloseTo(51.0, 0);
			expect(p.lng).toBeCloseTo(14.0, 1);
		});

		it('moves east at equator correctly', () => {
			// At equator, 1 degree lng ≈ 111.195 km
			const p = destinationPoint(0, 14.0, 90, 111.195);
			expect(p.lat).toBeCloseTo(0, 1);
			expect(p.lng).toBeCloseTo(15.0, 0);
		});

		it('round-trip: destination then bearing back should be ~reciprocal', () => {
			const start = { lat: 50.0, lng: 14.0 };
			const bearing = 45;
			const dist = 50; // km
			const dest = destinationPoint(start.lat, start.lng, bearing, dist);
			const returnBearing = bearingBetween(dest.lat, dest.lng, start.lat, start.lng);
			// Return bearing should be roughly the opposite (~225°)
			expect(returnBearing).toBeGreaterThan(220);
			expect(returnBearing).toBeLessThan(230);
		});

		it('round-trip: distance to destination matches input distance', () => {
			const dist = 100;
			const dest = destinationPoint(50.0, 14.0, 135, dist);
			const computed = distanceBetween(50.0, 14.0, dest.lat, dest.lng);
			expect(computed).toBeCloseTo(dist, 1);
		});
	});
});
