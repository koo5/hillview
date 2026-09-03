import { describe, expect, it } from 'bun:test';
import { angNorm, fitSummary, residual, unwrapDeltas } from './theilsen';

const pano = (n: number, fov: number, bias: number) =>
	Array.from({ length: n }, (_, i) => {
		const x = 0.02 + (0.96 * i) / (n - 1); // inset: the exact ±180° edge folds ambiguously
		return { x, delta: angNorm(bias + fov * (x - 0.5)) };
	});

describe('unwrapDeltas (mirror of calibrate.unwrap_deltas)', () => {
	it('leaves a centred 360° pano and an ordinary photo alone', () => {
		const p = pano(12, 360, 0);
		expect(unwrapDeltas(p, 409945, 10801)).toBe(0);
		expect(Math.abs(fitSummary(p, 100)!.fov - 360)).toBeLessThan(1);
		const q = pano(6, 60, 20);
		expect(unwrapDeltas(q, 4000, 3000)).toBe(0);
	});
	it('recovers a 360° pano whose compass is off-centre', () => {
		const p = pano(12, 360, 180); // half the points on each branch of the fold
		const naive = fitSummary(p.map((q) => ({ ...q })), 100)!;
		expect(Math.abs(naive.fov - 360) > 30 || naive.rms > 30).toBe(true);
		expect(unwrapDeltas(p, 409945, 10801)).toBeGreaterThan(0);
		const f = fitSummary(p, 100)!;
		expect(Math.abs(f.fov - 360)).toBeLessThan(1);
		expect(f.rms).toBeLessThan(0.1);
		expect(Math.abs(angNorm(f.centre_bias - 180))).toBeLessThan(1);
		expect(p.every((q) => Math.abs(residual(q, f)) < 1)).toBe(true);
	});
});
