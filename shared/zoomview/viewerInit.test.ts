import { describe, it, expect } from 'vitest';
import { initialSourceFor, swapInMainSource, OSD_VIEWER_DEFAULTS } from './viewerInit';
import type { DziPyramid } from './tileSource';

// Behavior-pinning tests for the extraction from OpenSeadragonViewer.svelte.

const PYRAMID: DziPyramid = {
	type: 'dzi', tiles_url: 'https://t/x_files', tile_size: 1024,
	overlap: 1, format: 'webp', width: 4096, height: 2048,
};

describe('OSD_VIEWER_DEFAULTS', () => {
	it('pins the main-app option values', () => {
		expect(OSD_VIEWER_DEFAULTS).toMatchObject({
			zoomPerScroll: 2.5, drawer: 'canvas', showNavigator: false,
			imageLoaderLimit: 1, maxZoomPixelRatio: 4, imageSmoothingEnabled: false,
		});
	});
});

describe('initialSourceFor', () => {
	it('fallback url → simple image source, flagged', () => {
		expect(initialSourceFor('https://thumb.webp', PYRAMID, 'https://full')).toEqual({
			usingFallback: true,
			source: { type: 'image', url: 'https://thumb.webp' },
		});
	});
	it('no fallback → main tile source directly', () => {
		const r = initialSourceFor(null, PYRAMID, 'https://full');
		expect(r.usingFallback).toBe(false);
		expect(r.source).toHaveProperty('Image');
	});
});

interface Handler { (e: { fullyLoaded: boolean }): void }

function mockWorld(items: object[]) {
	return {
		getItemAt: (i: number) => items[i],
		getItemCount: () => items.length,
		removeItem: (it: object) => { items.splice(items.indexOf(it), 1); },
	};
}

function mockMainItem(fullyLoaded: boolean) {
	const handlers: Handler[] = [];
	return {
		getFullyLoaded: () => fullyLoaded,
		addHandler: (_ev: string, h: Handler) => handlers.push(h),
		removeHandler: (_ev: string, h: Handler) => handlers.splice(handlers.indexOf(h), 1),
		fire: (e: { fullyLoaded: boolean }) => [...handlers].forEach((h) => h(e)),
		handlers,
	};
}

describe('swapInMainSource', () => {
	function run(fullyLoaded: boolean) {
		const fallback = { id: 'fallback' };
		const main = mockMainItem(fullyLoaded);
		const items: object[] = [fallback, main];
		const world = mockWorld(items);
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		let captured: any;
		const viewer = { world, addTiledImage: (opts: unknown) => { captured = opts; } };
		swapInMainSource(viewer, { type: 'image', url: 'x' });
		captured.success({ item: main });
		return { items, main, fallback, captured };
	}

	it('main already fully loaded → fallback removed immediately', () => {
		const { items, main } = run(true);
		expect(items).toEqual([main]);
	});

	it('not loaded yet → waits for fully-loaded-change, then removes fallback once', () => {
		const { items, main } = run(false);
		expect(items.length).toBe(2);
		main.fire({ fullyLoaded: false });      // partial event: no-op
		expect(items.length).toBe(2);
		main.fire({ fullyLoaded: true });
		expect(items).toEqual([main]);
		expect(main.handlers.length).toBe(0);   // handler removed after firing
	});

	it('does not remove when the world has a single item', () => {
		const main = mockMainItem(true);
		const items: object[] = [main];
		const world = mockWorld(items);
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		let captured: any;
		swapInMainSource({ world, addTiledImage: (o: unknown) => { captured = o; } }, {});
		captured.success({ item: main });
		expect(items).toEqual([main]);
	});

	it('error handler throws (surfaced to OSD), fallback stays', () => {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		let captured: any;
		const viewer = { world: mockWorld([{}]), addTiledImage: (o: unknown) => { captured = o; } };
		swapInMainSource(viewer, {});
		expect(() => captured.error({ message: 'boom' })).toThrow(/addTiledImage error: boom/);
	});
});
