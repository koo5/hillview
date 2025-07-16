import { writable, get } from 'svelte/store';
import { photoCaptureService, type DevicePhotoMetadata } from './photoCapture';
import { devicePhotos } from './stores';
import { removePlaceholder } from './placeholderInjector';

export interface CaptureLocation {
    latitude: number;
    longitude: number;
    altitude?: number | null;
    accuracy: number;
    heading?: number | null;
    source: 'gps' | 'map';
}

export interface CaptureQueueItem {
    id: string;
    blob: Blob;
    location: CaptureLocation;
    timestamp: number;
    mode: 'slow' | 'fast';
    placeholderId: string;
}

export interface QueueStats {
    size: number;
    processing: boolean;
    slowModeCount: number;
    fastModeCount: number;
    totalCaptured: number;
}

class CaptureQueueManager {
    private queue: CaptureQueueItem[] = [];
    private processing = false;
    private maxQueueSize = 50; // Default, can be configured
    private slowModeCount = 0;
    private fastModeCount = 0;
    
    // Store for queue statistics
    public stats = writable<QueueStats>({
        size: 0,
        processing: false,
        slowModeCount: 0,
        fastModeCount: 0,
        totalCaptured: 0
    });

    constructor() {
        // Start processing loop
        this.processLoop();
    }

    setMaxQueueSize(size: number): void {
        this.maxQueueSize = size;
    }

    async add(item: CaptureQueueItem): Promise<boolean> {
        // Check queue size limit
        if (this.queue.length >= this.maxQueueSize) {
            console.warn('Capture queue full, dropping oldest item');
            this.queue.shift(); // Remove oldest
        }

        this.queue.push(item);
        
        // Update counters
        if (item.mode === 'slow') {
            this.slowModeCount++;
        } else {
            this.fastModeCount++;
        }

        this.updateStats();
        return true;
    }

    private async processLoop(): Promise<void> {
        while (true) {
            if (this.queue.length > 0 && !this.processing) {
                await this.processNext();
            } else {
                // Wait a bit before checking again
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
    }

    private async processNext(): Promise<void> {
        const item = this.queue.shift();
        if (!item) return;

        this.processing = true;
        this.updateStats();

        try {
            // Convert blob to File
            const file = new File([item.blob], `photo_${item.timestamp}.jpg`, { type: 'image/jpeg' });
            
            // Prepare photo data
            const photoData = {
                image: file,
                location: {
                    latitude: item.location.latitude,
                    longitude: item.location.longitude,
                    altitude: item.location.altitude,
                    accuracy: item.location.accuracy
                },
                bearing: item.location.heading,
                timestamp: item.timestamp
            };

            // Save photo with EXIF
            const savedPhoto = await photoCaptureService.savePhotoWithExif(photoData);
            
            // Replace placeholder with real photo
            devicePhotos.update(photos => {
                const filtered = photos.filter(p => p.id !== item.placeholderId);
                return [...filtered, savedPhoto];
            });
            
            // Remove from placeholder store
            removePlaceholder(item.placeholderId);

            console.log(`Processed ${item.mode} mode photo:`, savedPhoto.id);
        } catch (error) {
            console.error('Failed to process queued photo:', error);
            
            // Remove placeholder on error
            devicePhotos.update(photos => photos.filter(p => p.id !== item.placeholderId));
            removePlaceholder(item.placeholderId);
        } finally {
            this.processing = false;
            this.updateStats();
        }
    }

    private updateStats(): void {
        this.stats.set({
            size: this.queue.length,
            processing: this.processing,
            slowModeCount: this.slowModeCount,
            fastModeCount: this.fastModeCount,
            totalCaptured: this.slowModeCount + this.fastModeCount
        });
    }

    reset(): void {
        this.queue = [];
        this.slowModeCount = 0;
        this.fastModeCount = 0;
        this.updateStats();
    }
}

export const captureQueue = new CaptureQueueManager();