import type { PhotoData, SourceConfig } from '../photoWorkerTypes';

export type SourceId = string; // TODO: move to photoWorkerTypes.ts

export class SourcePhotosState {
    private photos = new Map<SourceId, PhotoData[]>();

    getPhotosBySource(): Map<SourceId, PhotoData[]> {
        return this.photos;
    }

    getFlattenedPhotos(): PhotoData[] {
        const allPhotos: PhotoData[] = [];
        for (const sourcePhotos of this.photos.values()) {
            allPhotos.push(...sourcePhotos);
        }
        return allPhotos;
    }

    setSourcePhotos(sourceId: SourceId, photos: PhotoData[]): void {
        this.photos.set(sourceId, photos);
        console.log(`SourcePhotosState: Source ${sourceId} set to ${photos.length} photos`);
    }

    removePhoto(photoId: string, source: SourceId): number {
        const sourcePhotos = this.photos.get(source);
        if (!sourcePhotos) {
            console.log(`SourcePhotosState: No photos found for source ${source} when trying to remove photo ${photoId}`);
            return 0;
        }

        const updatedPhotos = sourcePhotos.filter(photo => photo.id !== photoId);
        this.photos.set(source, updatedPhotos);
        const removedCount = sourcePhotos.length - updatedPhotos.length;
        console.log(`SourcePhotosState: Removed photo ${photoId} from ${source} - ${removedCount} photos removed`);
        return removedCount;
    }

    removeUserPhotos(userId: string, source: SourceId): number {
        const sourcePhotos = this.photos.get(source);
        if (!sourcePhotos) {
            console.log(`SourcePhotosState: No photos found for source ${source} when trying to remove photos by user ${userId}`);
            return 0;
        }

        const beforeCount = sourcePhotos.length;
        const updatedPhotos = sourcePhotos.filter(photo => {
            const photoAny = photo as any;
            if (photoAny.creator?.id === userId) {
                console.log(`SourcePhotosState: Filtering out photo ${photo.id} by user ${userId}`);
                return false;
            }
            return true;
        });

        this.photos.set(source, updatedPhotos);
        const removedCount = beforeCount - updatedPhotos.length;
        console.log(`SourcePhotosState: Removed ${removedCount} photos by user ${userId} from ${source}`);
        return removedCount;
    }

    removePhotosFromDisabledSources(enabledSources: SourceConfig[]): void {
        const enabledSourceIds = new Set(
            enabledSources
                .filter(s => s.enabled)
                .map(s => s.id)
        );

        for (const sourceId of this.photos.keys()) {
            if (!enabledSourceIds.has(sourceId)) {
                console.log(`SourcePhotosState: Clearing photos from disabled source: ${sourceId}`);
                this.photos.delete(sourceId);
            }
        }
    }

    clear(): void {
        this.photos.clear();
        console.log('SourcePhotosState: Cleared all photos');
    }
}