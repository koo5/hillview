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

interface GridCell {
    photos: PhotoData[];
    nextIndex: number; // For round-robin within cell
}

interface SourceGrid {
    sourceId: SourceId;
    grid: Map<CellKey, GridCell>; // cellKey -> GridCell
    cellKeys: CellKey[]; // Ordered list of cells for iteration
    nextCellIndex: number; // For round-robin across cells
}

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
     * Apply smart culling to ensure uniform screen coverage
     */
    cullPhotos(photosPerSource: Map<SourceId, PhotoData[]>, maxPhotos: number): PhotoData[] {
        if (photosPerSource.size === 0 || maxPhotos <= 0) {
            return [];
        }

        // Build screen grid for each source
        const sourceGrids = this.buildSourceGrids(photosPerSource);
        
        if (sourceGrids.length === 0) {
            return [];
        }

        // Round-robin selection across sources and screen cells
        const selectedPhotos: PhotoData[] = [];
        let sourceIndex = 0;

        while (selectedPhotos.length < maxPhotos) {
            let foundPhoto = false;

            // Try each source in round-robin fashion
            for (let i = 0; i < sourceGrids.length && selectedPhotos.length < maxPhotos; i++) {
                const currentSourceIndex = (sourceIndex + i) % sourceGrids.length;
                const sourceGrid = sourceGrids[currentSourceIndex];

                const photo = this.selectNextPhotoFromSource(sourceGrid);
                if (photo) {
                    selectedPhotos.push(photo);
                    foundPhoto = true;
                }
            }

            // Move to next source for next iteration
            sourceIndex = (sourceIndex + 1) % sourceGrids.length;

            // If no source produced a photo in a full round, we're done
            if (!foundPhoto) {
                break;
            }
        }

        console.log(`CullingGrid: Culled ${photosPerSource.size} sources (${Array.from(photosPerSource.values()).reduce((sum, photos) => sum + photos.length, 0)} total photos) down to ${selectedPhotos.length} photos for uniform screen coverage`);
        
        return selectedPhotos;
    }

    private buildSourceGrids(photosPerSource: Map<SourceId, PhotoData[]>): SourceGrid[] {
        const sourceGrids: SourceGrid[] = [];

        for (const [sourceId, photos] of photosPerSource.entries()) {
            if (photos.length === 0) continue;

            const grid = new Map<string, GridCell>();
            
            // Distribute photos into screen grid cells
            for (const photo of photos) {
                const gridKey = this.getScreenGridKey(photo);
                
                if (!grid.has(gridKey)) {
                    grid.set(gridKey, { photos: [], nextIndex: 0 });
                }
                
                grid.get(gridKey)!.photos.push(photo);
            }

            // Get ordered list of cell keys for iteration (ensures consistent ordering)
            const cellKeys = Array.from(grid.keys()).sort();

            sourceGrids.push({
                sourceId,
                grid,
                cellKeys,
                nextCellIndex: 0
            });
        }

        return sourceGrids;
    }

    private selectNextPhotoFromSource(sourceGrid: SourceGrid): PhotoData | null {
        if (sourceGrid.cellKeys.length === 0) {
            return null;
        }

        // Try each screen cell in the source, starting from the next cell
        const startCellIndex = sourceGrid.nextCellIndex;
        
        for (let i = 0; i < sourceGrid.cellKeys.length; i++) {
            const cellIndex = (startCellIndex + i) % sourceGrid.cellKeys.length;
            const cellKey = sourceGrid.cellKeys[cellIndex];
            const cell = sourceGrid.grid.get(cellKey)!;

            // If this screen cell has photos available
            if (cell.nextIndex < cell.photos.length) {
                const photo = cell.photos[cell.nextIndex];
                cell.nextIndex++;

                // Move to next cell for next iteration
                sourceGrid.nextCellIndex = (cellIndex + 1) % sourceGrid.cellKeys.length;
                
                return photo;
            }
        }

        // No photos available in any screen cell of this source
        return null;
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
    updateBounds(newBounds: Bounds): void {
        this.bounds = newBounds;
        this.latRange = newBounds.top_left.lat - newBounds.bottom_right.lat;
        this.lngRange = newBounds.bottom_right.lng - newBounds.top_left.lng;
    }

    /**
     * Get statistics about screen coverage
     */
    getCoverageStats(photosPerSource: Map<SourceId, PhotoData[]>, culledPhotos: PhotoData[]): {
        totalPhotos: number;
        selectedPhotos: number;
        sourceStats: { sourceId: SourceId; original: number; selected: number; percentage: number }[];
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
            sourceId,
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