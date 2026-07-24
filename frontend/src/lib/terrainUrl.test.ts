import { describe, expect, it } from 'vitest';
import { parseTerrainRectParams } from './terrain.svelte';

const q = (s: string) => new URLSearchParams(s);

describe('parseTerrainRectParams (tx1..ty2, the namespaced twin)', () => {
	it('parses a complete param set', () => {
		const r = parseTerrainRectParams(q('tx1=0.25&ty1=0.01&tx2=0.5&ty2=0.03'))!;
		expect(r).toEqual({ x1: 0.25, y1: 0.01, x2: 0.5, y2: 0.03 });
	});

	it('normalizes seam-straddling x on parse', () => {
		const r = parseTerrainRectParams(q('tx1=1.3&ty1=0&tx2=1.55&ty2=0.02'))!;
		expect(r.x1).toBeCloseTo(0.3, 9);
		expect(r.x2).toBeCloseTo(0.55, 9);
	});

	it('ignores incomplete, non-finite, or degenerate rects', () => {
		expect(parseTerrainRectParams(q('tx1=0.1&ty1=0&tx2=0.5'))).toBeNull();
		expect(parseTerrainRectParams(q('tx1=abc&ty1=0&tx2=0.5&ty2=0.1'))).toBeNull();
		expect(parseTerrainRectParams(q('tx1=0.5&ty1=0&tx2=0.5&ty2=0.1'))).toBeNull();
		expect(parseTerrainRectParams(q(''))).toBeNull();
	});

	it("never collides with the photo zoom view's x1..y2", () => {
		expect(parseTerrainRectParams(q('x1=0.1&y1=0&x2=0.5&y2=0.1&photo=abc'))).toBeNull();
	});
});
