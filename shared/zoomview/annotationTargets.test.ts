import { describe, it, expect } from 'vitest';
import { targetToPixels, targetToNormalized, toW3cAnnotation } from './annotationTargets';

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
