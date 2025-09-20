import { describe, it, expect, beforeEach, vi } from 'vitest';
import { captureQueue, type CaptureQueueItem } from './captureQueue';
import { get } from 'svelte/store';

// Mock the photoCapture service
vi.mock('./photoCapture', () => ({
    photoCaptureService: {
        savePhotoWithExif: vi.fn().mockImplementation(async (data) => {
            // Simulate processing time
            await new Promise(resolve => setTimeout(resolve, 100));
            return {
                id: `photo_${Date.now()}`,
                filename: `photo_${data.timestamp}.jpg`,
                // ... other photo properties
            };
        })
    }
}));

// Mock stores
vi.mock('./stores', () => ({
    devicePhotos: {
        update: vi.fn()
    }
}));

vi.mock('./placeholderInjector', () => ({
    removePlaceholder: vi.fn()
}));

describe('CaptureQueue Parallel Processing', () => {
    beforeEach(() => {
        captureQueue.reset();
    });

    it('should process multiple items in parallel', async () => {
        // Set max concurrency to 3
        captureQueue.setMaxConcurrency(3);

        // Create 5 test items
        const items: CaptureQueueItem[] = [];
        for (let i = 0; i < 5; i++) {
            items.push({
                id: `item_${i}`,
                blob: new Blob(['test']),
                location: {
                    latitude: 0,
                    longitude: 0,
                    accuracy: 10,
                    locationSource: 'map' as const,
                    bearingSource: 'unknown'
                },
                timestamp: Date.now() + i,
                mode: 'fast',
                placeholderId: `placeholder_${i}`
            });
        }

        // Add all items to queue
        for (const item of items) {
            await captureQueue.add(item);
        }

        // Check initial stats
        let stats = get(captureQueue.stats);
        expect(stats.size).toBe(5);
        expect(stats.processingCount).toBe(0);

        // Wait a bit for processing to start
        await new Promise(resolve => setTimeout(resolve, 50));

        // Check that multiple items are being processed
        stats = get(captureQueue.stats);
        expect(stats.processingCount).toBeLessThanOrEqual(3);
        expect(stats.processingCount).toBeGreaterThan(0);

        // Wait for all processing to complete
        await new Promise(resolve => setTimeout(resolve, 500));

        // Check final stats
        stats = get(captureQueue.stats);
        expect(stats.size).toBe(0);
        expect(stats.processingCount).toBe(0);
        expect(stats.totalProcessed).toBe(5);
    });

    it('should respect max concurrency limit', async () => {
        // Set max concurrency to 2
        captureQueue.setMaxConcurrency(2);

        // Create 4 test items
        const items: CaptureQueueItem[] = [];
        for (let i = 0; i < 4; i++) {
            items.push({
                id: `item_${i}`,
                blob: new Blob(['test']),
                location: {
                    latitude: 0,
                    longitude: 0,
                    accuracy: 10,
                    locationSource: 'map' as const,
                    bearingSource: 'unknown'
                },
                timestamp: Date.now() + i,
                mode: 'slow',
                placeholderId: `placeholder_${i}`
            });
        }

        // Add all items
        for (const item of items) {
            await captureQueue.add(item);
        }

        // Wait for processing to start
        await new Promise(resolve => setTimeout(resolve, 50));

        // Check that concurrency limit is respected
        const stats = get(captureQueue.stats);
        expect(stats.processingCount).toBeLessThanOrEqual(2);
    });

    it('should handle errors gracefully in parallel processing', async () => {
        // Mock an error for one item
        const { photoCaptureService } = await import('./photoCapture');
        vi.mocked(photoCaptureService.savePhotoWithExif).mockImplementationOnce(async () => {
            throw new Error('Test error');
        });

        captureQueue.setMaxConcurrency(3);

        // Add items
        await captureQueue.add({
            id: 'error_item',
            blob: new Blob(['test']),
            location: { latitude: 0, longitude: 0, accuracy: 10, locationSource: 'map' as const, bearingSource: 'unknown' },
            timestamp: Date.now(),
            mode: 'fast',
            placeholderId: 'error_placeholder'
        });

        await captureQueue.add({
            id: 'good_item',
            blob: new Blob(['test']),
            location: { latitude: 0, longitude: 0, accuracy: 10, locationSource: 'map' as const, bearingSource: 'unknown' },
            timestamp: Date.now() + 1,
            mode: 'fast',
            placeholderId: 'good_placeholder'
        });

        // Wait for processing
        await new Promise(resolve => setTimeout(resolve, 300));

        // Check stats
        const stats = get(captureQueue.stats);
        expect(stats.totalFailed).toBe(1);
        expect(stats.totalProcessed).toBe(1);
    });
});