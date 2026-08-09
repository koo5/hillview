import { describe, it, expect } from 'vitest';
import {
	targetToPixels,
	targetToNormalized,
	toW3cAnnotation,
	targetRectNormalized,
	rectToViewBounds,
} from './annotationTargets';

// Behavior-pinning tests for the extraction from annotationApi.ts /
// OpenSeadragonViewer.svelte — these functions had no coverage before.

const RECT_TARGET = {
	selector: { type: 'RECTANGLE', geometry: { x: 0.25, y: 0.5, w: 0.1, h: 0.2 } },
};

describe('targetToPixels / targetToNormalized', () => {
	it('RECTANGLE geometry round-trips through pixel space', () => {
		const px = targetToPixels(RECT_TARGET, 1000, 500)!;
		expect((px.selector as { geometry: object }).geometry).toEqual({ x: 250, y: 250, w: 100, h: 100 });
		const back = targetToNormalized(px, 1000, 500)!;
		expect((back.selector as { geometry: object }).geometry).toEqual({ x: 0.25, y: 0.5, w: 0.1, h: 0.2 });
	});

	it('does not mutate the input', () => {
		const input = JSON.parse(JSON.stringify(RECT_TARGET));
		targetToPixels(input, 1000, 500);
		expect(input).toEqual(RECT_TARGET);
	});

	it('handles xywh=pixel: fragment selectors', () => {
		const t = { selector: { type: 'FragmentSelector', value: 'xywh=pixel:0.1,0.2,0.3,0.4' } };
		const px = targetToPixels(t, 100, 200)!;
		expect((px.selector as { value: string }).value).toBe('xywh=pixel:10,40,30,80');
	});

	it('array selectors keep array form; single selector stays single', () => {
		const arr = { selector: [RECT_TARGET.selector] };
		expect(Array.isArray(targetToPixels(arr, 100, 100)!.selector)).toBe(true);
		expect(Array.isArray(targetToPixels(RECT_TARGET, 100, 100)!.selector)).toBe(false);
	});

	it('null target / zero dims pass through untouched', () => {
		expect(targetToPixels(null, 100, 100)).toBeNull();
		expect(targetToPixels(RECT_TARGET, 0, 100)).toBe(RECT_TARGET);
		const noSel = { foo: 1 };
		expect(targetToPixels(noSel, 100, 100)).toEqual(noSel);
	});
});

describe('targetRectNormalized', () => {
	it('reads a RECTANGLE geometry', () => {
		expect(targetRectNormalized(RECT_TARGET)).toEqual({ x: 0.25, y: 0.5, w: 0.1, h: 0.2 });
	});

	it('reads an xywh=pixel: fragment selector', () => {
		const t = { selector: { type: 'FragmentSelector', value: 'xywh=pixel:0.1,0.2,0.3,0.4' } };
		expect(targetRectNormalized(t)).toEqual({ x: 0.1, y: 0.2, w: 0.3, h: 0.4 });
	});

	it('takes the first usable selector from an array', () => {
		const t = { selector: [{ type: 'other' }, RECT_TARGET.selector] };
		expect(targetRectNormalized(t)).toEqual({ x: 0.25, y: 0.5, w: 0.1, h: 0.2 });
	});

	it('is null for absent or unusable targets', () => {
		expect(targetRectNormalized(null)).toBeNull();
		expect(targetRectNormalized({})).toBeNull();
		expect(targetRectNormalized({ selector: { type: 'SvgSelector', value: '<svg/>' } })).toBeNull();
	});
});

describe('rectToViewBounds', () => {
	it('centres the window on the rect in width-normalized units', () => {
		// 2:1 image → aspect 0.5; rect y/h are height-normalized in the DB
		const b = rectToViewBounds({ x: 0.25, y: 0.5, w: 0.1, h: 0.2 }, 1000, 500, 3, 0)!;
		// osd: w=0.1, h=0.2*0.5=0.1, cx=0.3, cy=0.25+0.05=0.3, halves 0.15
		expect(b.x1).toBeCloseTo(0.15);
		expect(b.y1).toBeCloseTo(0.15);
		expect(b.x2).toBeCloseTo(0.45);
		expect(b.y2).toBeCloseTo(0.45);
	});

	it('floors the spans at a height fraction so point-sized labels keep context', () => {
		const b = rectToViewBounds({ x: 0.5, y: 0.5, w: 0.001, h: 0.001 }, 1000, 1000, 3, 0.12)!;
		expect(b.x2 - b.x1).toBeCloseTo(0.12);
		expect(b.y2 - b.y1).toBeCloseTo(0.12);
	});

	it('defaults to margins of 20% of each rect side — per axis, no squaring', () => {
		// 10:1 pano (aspect 0.1), box 0.1 wide × 0.05 osd-tall → 1.4× each side;
		// fitBounds letterboxes the window into the container, so the aspect
		// mismatch is the viewer's problem, not ours
		const b = rectToViewBounds({ x: 0.4, y: 0.2, w: 0.1, h: 0.5 }, 10000, 1000)!;
		expect(b.x2 - b.x1).toBeCloseTo(0.14);
		expect(b.x1).toBeCloseTo(0.38);
		expect(b.x2).toBeCloseTo(0.52);
		expect(b.y2 - b.y1).toBeCloseTo(0.07);
	});

	it('scales the optional floor with the image, not its width — pano regression', () => {
		// 10:1 pano (aspect 0.1): a width-relative floor would open a window
		// taller than the whole strip; height-relative stays proportionate.
		const b = rectToViewBounds({ x: 0.84, y: 0.2, w: 0.001, h: 0.001 }, 10000, 1000, 3, 0.15)!;
		expect(b.x2 - b.x1).toBeCloseTo(0.015); // 1.5% of pano width, not 36%
		expect(b.y1).toBeGreaterThanOrEqual(0); // clamped inside the strip
		expect(b.y2).toBeLessThanOrEqual(0.1);
	});

	it('clamps the window inside the image near an edge', () => {
		const b = rectToViewBounds({ x: 0.98, y: 0.5, w: 0.01, h: 0.01 }, 1000, 1000, 3, 0.15)!;
		expect(b.x2).toBeCloseTo(1); // pushed back from beyond the right edge
		expect(b.x1).toBeCloseTo(1 - 0.15); // floored span 0.15
	});

	it('is null without image dims', () => {
		expect(rectToViewBounds({ x: 0, y: 0, w: 1, h: 1 }, 0, 100)).toBeNull();
	});
});

describe('toW3cAnnotation', () => {
	it('builds the exact W3C shape with pixel-space target', () => {
		expect(toW3cAnnotation({ id: 'a1', body: 'Ještěd | hill', target: RECT_TARGET }, 1000, 500)).toEqual({
			'@context': 'http://www.w3.org/ns/anno.jsonld',
			id: 'a1',
			type: 'Annotation',
			body: [{ type: 'TextualBody', value: 'Ještěd | hill', purpose: 'commenting' }],
			target: { selector: { type: 'RECTANGLE', geometry: { x: 250, y: 250, w: 100, h: 100 } } },
		});
	});

	it('empty body → empty body array', () => {
		expect(toW3cAnnotation({ id: 'a2', body: null, target: RECT_TARGET }, 100, 100).body).toEqual([]);
	});
});
