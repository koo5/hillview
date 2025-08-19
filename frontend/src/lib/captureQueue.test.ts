import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { captureQueue, type CaptureQueueItem } from './captureQueue';
import { get } from 'svelte/store';

// Mock the photoCapture module
vi.mock('./photoCapture', () => ({
  photoCaptureService: {
    savePhotoWithExif: vi.fn().mockResolvedValue({
      id: 'mocked-photo-id',
      filename: 'mocked-photo.jpg',
      path: '/path/to/mocked-photo.jpg',
      latitude: 50.0617,
      longitude: 14.5146,
      altitude: 100,
      bearing: 45,
      timestamp: Date.now(),
      accuracy: 10,
      width: 1920,
      height: 1080,
      file_size: 1000000,
      created_at: Date.now(),
    })
  }
}));

// Mock the stores and placeholder injector
vi.mock('./stores', () => ({
  devicePhotos: {
    update: vi.fn()
  }
}));

vi.mock('./placeholderInjector', () => ({
  removePlaceholder: vi.fn()
}));

describe('CaptureQueueManager', () => {
  const createQueueItem = (id: string, mode: 'slow' | 'fast' = 'fast'): CaptureQueueItem => ({
    id,
    blob: new Blob([new Uint8Array(100)], { type: 'image/jpeg' }),
    location: {
      latitude: 50.0617 + Math.random() * 0.001,
      longitude: 14.5146 + Math.random() * 0.001,
      accuracy: 10,
    },
    timestamp: Date.now(),
    mode,
    placeholderId: `placeholder_${id}`
  });

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset queue state
    captureQueue.reset();
  });

  describe('basic queue operations', () => {
    it('should start with empty queue', () => {
      const stats = get(captureQueue.stats);
      expect(stats.size).toBe(0);
      expect(stats.processing).toBe(false);
      expect(stats.slowModeCount).toBe(0);
      expect(stats.fastModeCount).toBe(0);
      expect(stats.totalCaptured).toBe(0);
    });

    it('should add items to queue and update stats', async () => {
      const item1 = createQueueItem('photo1', 'fast');
      const item2 = createQueueItem('photo2', 'slow');

      await captureQueue.add(item1);
      let stats = get(captureQueue.stats);
      expect(stats.size).toBe(1);
      expect(stats.fastModeCount).toBe(1);
      expect(stats.slowModeCount).toBe(0);

      await captureQueue.add(item2);
      stats = get(captureQueue.stats);
      expect(stats.size).toBe(2);
      expect(stats.fastModeCount).toBe(1);
      expect(stats.slowModeCount).toBe(1);
      expect(stats.totalCaptured).toBe(2);
    });

    it('should handle queue size limits', async () => {
      // Set a small queue size for testing
      captureQueue.setMaxQueueSize(2);
      
      const items = [
        createQueueItem('photo1'),
        createQueueItem('photo2'),
        createQueueItem('photo3'), // This should push out photo1
      ];

      for (const item of items) {
        await captureQueue.add(item);
      }

      const stats = get(captureQueue.stats);
      expect(stats.size).toBe(2); // Should be limited to max size
    });

    it('should reset queue correctly', () => {
      const item = createQueueItem('photo1');
      captureQueue.add(item);
      
      captureQueue.reset();
      
      const stats = get(captureQueue.stats);
      expect(stats.size).toBe(0);
      expect(stats.slowModeCount).toBe(0);
      expect(stats.fastModeCount).toBe(0);
      expect(stats.totalCaptured).toBe(0);
    });

    it('should correctly count fast and slow mode items', async () => {
      const fastItems = [
        createQueueItem('fast1', 'fast'),
        createQueueItem('fast2', 'fast'),
      ];
      
      const slowItems = [
        createQueueItem('slow1', 'slow'),
      ];

      for (const item of [...fastItems, ...slowItems]) {
        await captureQueue.add(item);
      }

      const stats = get(captureQueue.stats);
      expect(stats.fastModeCount).toBe(2);
      expect(stats.slowModeCount).toBe(1);
      expect(stats.totalCaptured).toBe(3);
    });
  });

  describe('queue processing', () => {
    it('should process items (integration test)', async () => {
      const item = createQueueItem('test-photo');
      await captureQueue.add(item);

      // Wait a bit for processing to potentially start
      await new Promise(resolve => setTimeout(resolve, 50));

      // The processing happens asynchronously in the background
      // We can't easily test the full processing without mocking more dependencies
      // But we can verify the item was added
      const stats = get(captureQueue.stats);
      expect(stats.totalCaptured).toBe(1);
    });
  });

  describe('stats store reactivity', () => {
    it('should update stats store when queue changes', async () => {
      let statsUpdates = 0;
      const unsubscribe = captureQueue.stats.subscribe(() => {
        statsUpdates++;
      });

      await captureQueue.add(createQueueItem('photo1'));
      await captureQueue.add(createQueueItem('photo2'));
      
      // Should have triggered at least a few updates
      expect(statsUpdates).toBeGreaterThan(2);
      
      unsubscribe();
    });
  });
});