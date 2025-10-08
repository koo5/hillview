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
     * Apply priority-based culling with hash deduplication and lazy evaluation
     */
    cullPhotos(photosPerSource: Map<SourceId, PhotoData[]>, maxPhotos: number): PhotoData[] {
        if (photosPerSource.size === 0 || maxPhotos <= 0) {
            return [];
        }

        const totalCells = this.GRID_SIZE * this.GRID_SIZE;
        const photosPerCell = Math.max(1, Math.floor(maxPhotos / totalCells));

        // Create grid to store photos by cell
        const cellGrid = new Map<CellKey, CellPhotos>();

        // Process each grid cell lazily
        for (let row = 0; row < this.GRID_SIZE; row++) {
            for (let col = 0; col < this.GRID_SIZE; col++) {
                const cellKey: CellKey = `${row},${col}`;
                const cellData: CellPhotos = { photos: [], hashToIndex: new Map() };

                this.fillCell(cellKey, cellData, photosPerSource, photosPerCell);

                if (cellData.photos.length > 0) {
                    cellGrid.set(cellKey, cellData);
                }
            }
        }

        // Flatten all photos from cells
        const selectedPhotos: PhotoData[] = [];
        for (const cellData of cellGrid.values()) {
            selectedPhotos.push(...cellData.photos);
        }

        // Limit to maxPhotos if we exceeded
        const finalPhotos = selectedPhotos.slice(0, maxPhotos);

        console.log(`CullingGrid: Priority-culled ${photosPerSource.size} sources (${Array.from(photosPerSource.values()).reduce((sum, photos) => sum + photos.length, 0)} total photos) down to ${finalPhotos.length} photos with geographic distribution`);

        return finalPhotos;
    }

    private fillCell(cellKey: CellKey, cellData: CellPhotos, photosPerSource: Map<SourceId, PhotoData[]>, photosPerCell: number): void {
        let photosNeeded = photosPerCell;

        // Process sources by priority (1 = highest priority)
        const priorities = [1, 2, 3, 4] as const;

        for (const priority of priorities) {
            if (photosNeeded <= 0) break;

            for (const [sourceId, photos] of photosPerSource.entries()) {
                if (photosNeeded <= 0) break;

                const sourcePriority = this.getSourcePriority(sourceId);
                if (sourcePriority !== priority) continue;

                const photosInCell = this.getPhotosInCell(photos, cellKey);
                if (photosInCell.length === 0) continue;

                if (priority === SOURCE_PRIORITY.device) {
                    // Priority 1: Device photos (take first N, already sorted by created_at DESC)
                    const toTake = Math.min(photosNeeded, photosInCell.length);
                    const devicePhotos = photosInCell.slice(0, toTake);

                    // Add to cell and build hash index
                    for (const photo of devicePhotos) {
                        const index = cellData.photos.length;
                        cellData.photos.push(photo);

                        if (photo.fileHash) {
                            cellData.hashToIndex.set(photo.fileHash, index);
                        }
                    }

                    photosNeeded -= devicePhotos.length;

                } else if (priority === SOURCE_PRIORITY.hillview) {
                    // Priority 2: Hillview photos with hash replacement (already sorted by created_at DESC)
                    for (const hillviewPhoto of photosInCell) {
                        if (photosNeeded <= 0) break;

                        if (hillviewPhoto.fileHash) {
                            const matchIndex = cellData.hashToIndex.get(hillviewPhoto.fileHash);
                            if (matchIndex !== undefined) {
                                // Replace device photo with hillview photo (embed device photo)
                                const devicePhoto = cellData.photos[matchIndex];
                                cellData.photos[matchIndex] = {
                                    ...hillviewPhoto,
                                    device_photo: devicePhoto
                                } as PhotoData;
                                continue; // Don't decrement photosNeeded for replacement
                            }
                        }

                        // No duplicate found, add new hillview photo
                        cellData.photos.push(hillviewPhoto);
                        photosNeeded--;
                    }

                } else {
                    // Priority 3 & 4: Other sources (order doesn't matter, just take first N)
                    const toTake = Math.min(photosNeeded, photosInCell.length);
                    cellData.photos.push(...photosInCell.slice(0, toTake));
                    photosNeeded -= toTake;
                }
            }
        }
    }

    private getSourcePriority(sourceId: SourceId): Priority {
        if (sourceId === 'device') return SOURCE_PRIORITY.device;
        if (sourceId === 'hillview') return SOURCE_PRIORITY.hillview;
        if (sourceId === 'mapillary') return SOURCE_PRIORITY.mapillary;
        return SOURCE_PRIORITY.other;
    }

    private getPhotosInCell(photos: PhotoData[], cellKey: CellKey): PhotoData[] {
        const photosInCell: PhotoData[] = [];

        for (const photo of photos) {
            if (this.getScreenGridKey(photo) === cellKey) {
                photosInCell.push(photo);
            }
        }

        return photosInCell;
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