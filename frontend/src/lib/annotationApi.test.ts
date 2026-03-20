import { describe, it, expect } from 'vitest';
import { targetToPixels, targetToNormalized } from './annotationApi';

describe('annotation coordinate transforms', () => {
	const IMG_W = 1000;
	const IMG_H = 500;

	describe('targetToNormalized', () => {
		it('returns null target as-is', () => {
			expect(targetToNormalized(null, IMG_W, IMG_H)).toBeNull();
		});

		it('returns target unchanged when imgWidth is 0', () => {
			const target = { selector: { type: 'RECTANGLE', geometry: { x: 100, y: 50, w: 200, h: 100 } } };
			const result = targetToNormalized(target, 0, IMG_H);
			expect(result).toEqual(target);
		});

		it('returns target unchanged when imgHeight is 0', () => {
			const target = { selector: { type: 'RECTANGLE', geometry: { x: 100, y: 50, w: 200, h: 100 } } };
			const result = targetToNormalized(target, IMG_W, 0);
			expect(result).toEqual(target);
		});

		it('normalizes RECTANGLE geometry', () => {
			const target = {
				selector: {
					type: 'RECTANGLE',
					geometry: { x: 100, y: 50, w: 200, h: 100 },
				},
			};
			const result = targetToNormalized(target, IMG_W, IMG_H);
			expect(result!.selector.geometry.x).toBeCloseTo(0.1);
			expect(result!.selector.geometry.y).toBeCloseTo(0.1);
			expect(result!.selector.geometry.w).toBeCloseTo(0.2);
			expect(result!.selector.geometry.h).toBeCloseTo(0.2);
		});

		it('normalizes FragmentSelector xywh', () => {
			const target = {
				selector: {
					type: 'FragmentSelector',
					value: 'xywh=pixel:100,50,200,100',
				},
			};
			const result = targetToNormalized(target, IMG_W, IMG_H);
			expect(result!.selector.value).toBe('xywh=pixel:0.1,0.1,0.2,0.2');
		});

		it('does not mutate the original target', () => {
			const original = {
				selector: {
					type: 'RECTANGLE',
					geometry: { x: 100, y: 50, w: 200, h: 100 },
				},
			};
			const origCopy = JSON.parse(JSON.stringify(original));
			targetToNormalized(original, IMG_W, IMG_H);
			expect(original).toEqual(origCopy);
		});

		it('handles array of selectors', () => {
			const target = {
				selector: [
					{ type: 'RECTANGLE', geometry: { x: 500, y: 250, w: 100, h: 50 } },
					{ type: 'FragmentSelector', value: 'xywh=pixel:500,250,100,50' },
				],
			};
			const result = targetToNormalized(target, IMG_W, IMG_H);
			// Should remain an array
			expect(Array.isArray(result!.selector)).toBe(true);
			const selectors = result!.selector as any[];
			expect(selectors[0].geometry.x).toBeCloseTo(0.5);
			expect(selectors[0].geometry.y).toBeCloseTo(0.5);
			expect(selectors[1].value).toBe('xywh=pixel:0.5,0.5,0.1,0.1');
		});

		it('passes through target with no selector', () => {
			const target = { source: 'some-image.jpg' };
			const result = targetToNormalized(target, IMG_W, IMG_H);
			expect(result).toEqual(target);
		});

		it('passes through unknown selector types', () => {
			const target = { selector: { type: 'SvgSelector', value: '<svg>...</svg>' } };
			const result = targetToNormalized(target, IMG_W, IMG_H);
			expect(result).toEqual(target);
		});
	});

	describe('targetToPixels', () => {
		it('returns null target as-is', () => {
			expect(targetToPixels(null, IMG_W, IMG_H)).toBeNull();
		});

		it('denormalizes RECTANGLE geometry', () => {
			const target = {
				selector: {
					type: 'RECTANGLE',
					geometry: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
				},
			};
			const result = targetToPixels(target, IMG_W, IMG_H);
			expect(result!.selector.geometry.x).toBeCloseTo(100);
			expect(result!.selector.geometry.y).toBeCloseTo(50);
			expect(result!.selector.geometry.w).toBeCloseTo(200);
			expect(result!.selector.geometry.h).toBeCloseTo(100);
		});

		it('denormalizes FragmentSelector xywh', () => {
			const target = {
				selector: {
					type: 'FragmentSelector',
					value: 'xywh=pixel:0.1,0.1,0.2,0.2',
				},
			};
			const result = targetToPixels(target, IMG_W, IMG_H);
			expect(result!.selector.value).toBe('xywh=pixel:100,50,200,100');
		});
	});

	describe('round-trip: normalize → denormalize', () => {
		it('round-trips RECTANGLE correctly', () => {
			const original = {
				selector: {
					type: 'RECTANGLE',
					geometry: { x: 300, y: 150, w: 400, h: 200 },
				},
			};
			const normalized = targetToNormalized(original, IMG_W, IMG_H);
			const restored = targetToPixels(normalized, IMG_W, IMG_H);
			expect(restored!.selector.geometry.x).toBeCloseTo(300);
			expect(restored!.selector.geometry.y).toBeCloseTo(150);
			expect(restored!.selector.geometry.w).toBeCloseTo(400);
			expect(restored!.selector.geometry.h).toBeCloseTo(200);
		});

		it('round-trips FragmentSelector correctly', () => {
			const original = {
				selector: {
					type: 'FragmentSelector',
					value: 'xywh=pixel:300,150,400,200',
				},
			};
			const normalized = targetToNormalized(original, IMG_W, IMG_H);
			const restored = targetToPixels(normalized, IMG_W, IMG_H);
			expect(restored!.selector.value).toBe('xywh=pixel:300,150,400,200');
		});

		it('round-trips array selectors correctly', () => {
			const original = {
				selector: [
					{ type: 'RECTANGLE', geometry: { x: 100, y: 200, w: 300, h: 100 } },
				],
			};
			const normalized = targetToNormalized(original, IMG_W, IMG_H);
			const restored = targetToPixels(normalized, IMG_W, IMG_H);
			const sel = (restored!.selector as any[])[0];
			expect(sel.geometry.x).toBeCloseTo(100);
			expect(sel.geometry.y).toBeCloseTo(200);
			expect(sel.geometry.w).toBeCloseTo(300);
			expect(sel.geometry.h).toBeCloseTo(100);
		});

		it('round-trips with different image dimensions', () => {
			const widths = [640, 1920, 4000];
			const heights = [480, 1080, 3000];
			for (let i = 0; i < widths.length; i++) {
				const w = widths[i];
				const h = heights[i];
				const original = {
					selector: {
						type: 'RECTANGLE',
						geometry: { x: w / 4, y: h / 4, w: w / 2, h: h / 2 },
					},
				};
				const normalized = targetToNormalized(original, w, h);
				// Normalized values should be 0.25 and 0.5
				expect(normalized!.selector.geometry.x).toBeCloseTo(0.25);
				expect(normalized!.selector.geometry.w).toBeCloseTo(0.5);
				const restored = targetToPixels(normalized, w, h);
				expect(restored!.selector.geometry.x).toBeCloseTo(w / 4);
				expect(restored!.selector.geometry.w).toBeCloseTo(w / 2);
			}
		});
	});
});
