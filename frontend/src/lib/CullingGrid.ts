/**
 * Culling Grid - Smart Photo Selection for Screen Coverage
 *
 * Ensures uniform visual distribution across the screen by:
 * 1. Creating a 10x10 virtual grid over the current viewport bounds
 * 2. Round-robin selection: For each source → For each screen cell → Take 1 photo
 * 3. Continue until the limit is reached
 *
 * This prevents visual clustering and ensures good screen coverage across all
 * visible areas, giving users a well-distributed overview of the entire viewport.
 */

import type { PhotoData, Bounds } from './photoWorkerTypes';

// Type aliases for clarity
export type SourceId = string;
export type CellKey = string; // Format: "row,col" e.g. "3,7"
export type FileHash = string;
export type PhotoIndex = number;
export type Priority = 1 | 2 | 3 | 4; // 1 = highest priority

// Source priority levels (lower number = higher priority)
const SOURCE_PRIORITY: Record<SourceId, Priority> = {
    'device': 1,
    'hillview': 2,
    'other': 3,
    'mapillary': 4
} as const;

interface CellPhotos {
    photos: PhotoData[];
    hashToIndex: Map<FileHash, PhotoIndex>; // For efficient duplicate detection
}

export class CullingGrid {
    private readonly GRID_SIZE = 10;
    private bounds: Bounds;
    private latRange: number;
    private lngRange: number;

    constructor(bounds: Bounds) {
        this.bounds = bounds;
        this.latRange = bounds.top_left.lat - bounds.bottom_right.lat;
        this.lngRange = bounds.bottom_right.lng - bounds.top_left.lng;
    }

    /**
     * Apply priority-based culling with hash deduplication and round-robin selection
     * Matches Kotlin implementation: true round-robin across all cells until maxPhotos reached
     */
    cullPhotos(photosPerSource: Map<SourceId, PhotoData[]>, maxPhotos: number): PhotoData[] {
        if (photosPerSource.size === 0 || maxPhotos <= 0) {
            return [];
        }

        // Create grid to store photos by cell
        const cellGrid = new Map<CellKey, CellPhotos>();

        // Sort sources by priority (device first, mapillary last)
        const sortedSourceIds = Array.from(photosPerSource.keys()).sort((a, b) => {
            return this.getSourcePriority(a) - this.getSourcePriority(b);
        });

        // Populate grid cells with photos from each source (by priority order)
        for (const sourceId of sortedSourceIds) {
            const photos = photosPerSource.get(sourceId);
            if (!photos) continue;

            for (const photo of photos) {
                const cellKey = this.getScreenGridKey(photo);

                // Get or create cell
                let cellData = cellGrid.get(cellKey);
                if (!cellData) {
                    cellData = { photos: [], hashToIndex: new Map() };
                    cellGrid.set(cellKey, cellData);
                }

                // Check for duplicates using file hash
                if (photo.file_hash && cellData.hashToIndex.has(photo.file_hash)) {
                    continue; // Skip duplicate photo
                }

                // Add hash mapping if present
                if (photo.file_hash) {
                    cellData.hashToIndex.set(photo.file_hash, cellData.photos.length);
                }

                cellData.photos.push(photo);
            }
        }

        // Round-robin selection across all cells until maxPhotos reached
        const result: PhotoData[] = [];
        const cellIterators = Array.from(cellGrid.values()).map(cell => ({
            photos: cell.photos,
            index: 0
        }));

        let round = 0;
        while (result.length < maxPhotos && cellIterators.length > 0) {
            round++;
            const exhaustedIndices: number[] = [];

            for (let i = cellIterators.length - 1; i >= 0; i--) {
                if (result.length >= maxPhotos) break;

                const iterator = cellIterators[i];
                if (iterator.index < iterator.photos.length) {
                    result.push(iterator.photos[iterator.index]);
                    iterator.index++;
                } else {
                    exhaustedIndices.push(i);
                }
            }

            // Remove exhausted iterators
            for (const index of exhaustedIndices) {
                cellIterators.splice(index, 1);
            }
        }

        console.log(`CullingGrid: Round-robin culled ${photosPerSource.size} sources (${Array.from(photosPerSource.values()).reduce((sum, photos) => sum + photos.length, 0)} total photos) down to ${result.length} photos in ${round} rounds across ${cellGrid.size} cells`);

        return result;
    }

    private getSourcePriority(sourceId: SourceId): Priority {
        if (sourceId === 'device') return SOURCE_PRIORITY.device;
        if (sourceId === 'hillview') return SOURCE_PRIORITY.hillview;
        if (sourceId === 'mapillary') return SOURCE_PRIORITY.mapillary;
        return SOURCE_PRIORITY.other;
    }

    private getScreenGridKey(photo: PhotoData): CellKey {
        // Calculate position within viewport bounds (0-1)
        const latPos = (this.bounds.top_left.lat - photo.coord.lat) / this.latRange;
        const lngPos = (photo.coord.lng - this.bounds.top_left.lng) / this.lngRange;

        // Convert to 0-9 screen grid cells (clamp to ensure valid range)
        const gridLat = Math.min(this.GRID_SIZE - 1, Math.max(0, Math.floor(latPos * this.GRID_SIZE)));
        const gridLng = Math.min(this.GRID_SIZE - 1, Math.max(0, Math.floor(lngPos * this.GRID_SIZE)));

        return `${gridLat},${gridLng}`;
    }

    /**
     * Update bounds for the screen grid (call when viewport changes)
     */
    /*updateBounds(newBounds: Bounds): void {
        this.bounds = newBounds;
        this.latRange = newBounds.top_left.lat - newBounds.bottom_right.lat;
        this.lngRange = newBounds.bottom_right.lng - newBounds.top_left.lng;
    }*/

    /**
     * Get statistics about screen coverage
     */
    getCoverageStats(photosPerSource: Map<SourceId, PhotoData[]>, culledPhotos: PhotoData[]): {
        totalPhotos: number;
        selectedPhotos: number;
        sourceStats: { source_id: SourceId; original: number; selected: number; percentage: number }[];
        screenCoverage: { cellKey: CellKey; photoCount: number }[];
        emptyCells: number;
        totalCells: number;
    } {
        const totalPhotos = Array.from(photosPerSource.values()).reduce((sum, photos) => sum + photos.length, 0);

        // Count photos per source in result
        const selectedPerSource = new Map<string, number>();
        const selectedPerCell = new Map<string, number>();

        for (const photo of culledPhotos) {
            const sourceId = photo.source?.id || 'unknown';
            selectedPerSource.set(sourceId, (selectedPerSource.get(sourceId) || 0) + 1);

            const gridKey = this.getScreenGridKey(photo);
            selectedPerCell.set(gridKey, (selectedPerCell.get(gridKey) || 0) + 1);
        }

        const sourceStats = Array.from(photosPerSource.entries()).map(([sourceId, photos]) => ({
            source_id: sourceId,
            original: photos.length,
            selected: selectedPerSource.get(sourceId) || 0,
            percentage: photos.length > 0 ? ((selectedPerSource.get(sourceId) || 0) / photos.length) * 100 : 0
        }));

        const screenCoverage = Array.from(selectedPerCell.entries()).map(([cellKey, photoCount]) => ({
            cellKey,
            photoCount
        }));

        const totalCells = this.GRID_SIZE * this.GRID_SIZE;
        const emptyCells = totalCells - selectedPerCell.size;

        return {
            totalPhotos,
            selectedPhotos: culledPhotos.length,
            sourceStats,
            screenCoverage,
            emptyCells,
            totalCells
        };
    }
}
