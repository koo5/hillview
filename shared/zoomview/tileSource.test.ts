import { describe, it, expect } from 'vitest';
import { buildTileSource, computeMinLevel, type DziPyramid } from './tileSource';

// Behavior-pinning tests for the extraction from OpenSeadragonViewer.svelte —
// values verified against the pre-extraction implementation.

// A real pyramid from production (Prosecké skály east pano).
const PANO: DziPyramid = {
	type: 'dzi',
	dzi_url: 'https://pics.hillview.cz/opt/dzi/x/y.dzi',
	tiles_url: 'https://pics.hillview.cz/opt/dzi/x/y_files',
	tile_size: 1024,
	overlap: 1,
	format: 'webp',
	width: 66897,
	height: 5133,
};

describe('computeMinLevel', () => {
	it('finds the last level fitting one tile (66897px, 1024 tiles → 10)', () => {
		// maxLevel = ceil(log2(66897)) = 17; level 10 → ceil(66897/128) = 523 ≤ 1024,
		// level 11 → ceil(66897/64) = 1046 > 1024
		expect(computeMinLevel(66897, 5133, 1024)).toBe(10);
	});
	it('image smaller than a tile → top level', () => {
		expect(computeMinLevel(800, 600, 1024)).toBe(10); // ceil(log2(800)) = 10
	});
	it('uses the larger dimension', () => {
		expect(computeMinLevel(5133, 66897, 1024)).toBe(10);
	});
	it('exact power-of-two boundary', () => {
		// 4096: maxLevel 12; level 10 → 1024 ≤ 1024 ✓; level 11 → 2048 ✗
		expect(computeMinLevel(4096, 4096, 1024)).toBe(10);
	});
});

describe('buildTileSource', () => {
	it('builds the exact DZI descriptor shape', () => {
		expect(buildTileSource(PANO, 'https://fallback')).toEqual({
			Image: {
				xmlns: 'http://schemas.microsoft.com/deepzoom/2008',
				Url: 'https://pics.hillview.cz/opt/dzi/x/y_files/',
				Format: 'webp',
				Overlap: '1',
				TileSize: '1024',
				Size: { Width: '66897', Height: '5133' },
			},
			minLevel: 10,
		});
	});
	it('no pyramid → single-image fallback', () => {
		expect(buildTileSource(undefined, 'https://full.jpg')).toEqual({
			type: 'image',
			url: 'https://full.jpg',
		});
		expect(buildTileSource(null, 'https://full.jpg')).toEqual({
			type: 'image',
			url: 'https://full.jpg',
		});
	});
	it('non-dzi pyramid type → fallback', () => {
		expect(buildTileSource({ ...PANO, type: 'iiif' }, 'https://full.jpg')).toEqual({
			type: 'image',
			url: 'https://full.jpg',
		});
	});
});
