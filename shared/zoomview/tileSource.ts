/**
 * Pure tile-source construction for OpenSeadragon — extracted verbatim from
 * OpenSeadragonViewer.svelte so it can be reused outside the main app (the
 * enrichment workbench embeds OSD viewers against the same DZI pyramids).
 *
 * Deliberately dependency-free: no stores, no $lib imports. The pyramid type
 * is structural (matches PyramidMetadata in types/photoCommon.ts) so this
 * module can be consumed from another app without dragging frontend types in.
 */

export interface DziPyramid {
	type: string; // 'dzi' — anything else falls back to a single image
	dzi_url?: string;
	tiles_url: string;
	tile_size: number;
	overlap: number;
	format: string;
	width: number;
	height: number;
}

export function computeMinLevel(width: number, height: number, tileSize: number): number {
	const maxDim = Math.max(width, height);
	const maxLevel = Math.ceil(Math.log2(maxDim));
	// Walk from the top level down; the first level where the image fits
	// in a single tile is the last one we want.  Everything below is waste.
	for (let level = maxLevel; level >= 0; level--) {
		const levelDim = Math.ceil(maxDim / Math.pow(2, maxLevel - level));
		if (levelDim <= tileSize) return level;
	}
	return 0;
}

export function buildTileSource(pyramid: DziPyramid | null | undefined, fallbackUrl: string) {
	const p = pyramid;
	if (p && p.type === 'dzi') {
		const minLevel = computeMinLevel(p.width, p.height, p.tile_size);
		console.log('[OSD] Using DZI pyramid for tile source:', p, '| minLevel:', minLevel);
		return {
			Image: {
				xmlns: 'http://schemas.microsoft.com/deepzoom/2008',
				Url: p.tiles_url + '/',
				Format: p.format,
				Overlap: String(p.overlap),
				TileSize: String(p.tile_size),
				Size: {
					Width: String(p.width),
					Height: String(p.height),
				},
			},
			minLevel,
			// crossOriginPolicy: 'Anonymous', // only needed for WebGL; causes CORS cache poisoning with fallback images
		};
	}
	// Fallback: single full-size image
	console.warn('[OSD] No DZI pyramid available, falling back to single-image source: ', JSON.stringify(p));
	return {
		type: 'image',
		url: fallbackUrl,
	};
}
