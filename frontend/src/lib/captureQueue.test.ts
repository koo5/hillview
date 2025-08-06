import { describe, it, expect, beforeEach, vi } from 'vitest';
import { captureQueue } from './captureQueue';
import type { CapturedPhotoData } from './types/photoTypes';

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

describe('CaptureQueue', () => {
  let queue: typeof captureQueue;
  const mockOnProgress = vi.fn();
  const mockOnComplete = vi.fn();
  const mockOnError = vi.fn();

  const createCapturedPhoto = (id: string): CapturedPhotoData => ({
    image: new File(['test'], `${id}.jpg`, { type: 'image/jpeg' }),
    location: {
      latitude: 50.0617 + Math.random() * 0.001,
      longitude: 14.5146 + Math.random() * 0.001,
      altitude: 100 + Math.random() * 10,
      accuracy: 10,
    },
    bearing: Math.random() * 360,
    timestamp: Date.now(),
  });

  beforeEach(() => {
    vi.clearAllMocks();
    queue = captureQueue;
    // Set up callbacks
    queue.onProgress = mockOnProgress;
    queue.onComplete = mockOnComplete;
    queue.onError = mockOnError;
  });

  describe('queue management', () => {
    it('should start with empty queue', () => {
      expect(queue.getQueueLength()).toBe(0);
      expect(queue.getStatus()).toEqual({
        queueLength: 0,
        processing: false,
        currentItem: null,
        processedCount: 0,
        errorCount: 0,
      });
    });

    it('should add items to queue', async () => {
      const photo1 = createCapturedPhoto('photo1');
      const photo2 = createCapturedPhoto('photo2');

      await queue.add(photo1);
      expect(queue.getQueueLength()).toBe(1);

      await queue.add(photo2);
      expect(queue.getQueueLength()).toBe(2);
    });

    it('should process queue items in order', async () => {
      const photos = [
        createCapturedPhoto('photo1'),
        createCapturedPhoto('photo2'),
        createCapturedPhoto('photo3'),
      ];

      for (const photo of photos) {
        await queue.add(photo);
      }

      // Wait for processing to complete
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnProgress).toHaveBeenCalledTimes(3);
      expect(mockOnComplete).toHaveBeenCalledTimes(3);
      expect(queue.getStatus().processedCount).toBe(3);
    });

    it('should handle concurrent additions', async () => {
      const photos = Array.from({ length: 10 }, (_, i) => 
        createCapturedPhoto(`photo${i}`)
      );

      // Add all photos concurrently
      await Promise.all(photos.map(photo => queue.add(photo)));

      expect(queue.getQueueLength()).toBe(10);
    });
  });

  describe('error handling', () => {
    it('should handle processing errors', async () => {
      // Mock savePhotoWithExif to throw an error
      const { photoCaptureService } = await import('./photoCapture');
      vi.mocked(photoCaptureService.savePhotoWithExif).mockRejectedValueOnce(new Error('Processing failed'));

      const photo = createCapturedPhoto('error-photo');
      await queue.add(photo);

      // Wait for processing
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnError).toHaveBeenCalledWith(
        expect.any(Error),
        expect.objectContaining({
          image: photo.image,
        })
      );
      expect(queue.getStatus().errorCount).toBe(1);
    });

    it('should continue processing after error', async () => {
      const { photoCaptureService } = await import('./photoCapture');
      vi.mocked(photoCaptureService.savePhotoWithExif)
        .mockRejectedValueOnce(new Error('First photo failed'))
        .mockResolvedValueOnce({
          id: 'success-photo',
          filename: 'success.jpg',
          path: '/path/to/success.jpg',
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
        });

      await queue.add(createCapturedPhoto('error-photo'));
      await queue.add(createCapturedPhoto('success-photo'));

      // Wait for processing
      await new Promise(resolve => setTimeout(resolve, 150));

      expect(mockOnError).toHaveBeenCalledOnce();
      expect(mockOnComplete).toHaveBeenCalledOnce();
      expect(queue.getStatus().errorCount).toBe(1);
      expect(queue.getStatus().processedCount).toBe(1);
    });
  });

  describe('status tracking', () => {
    it('should track processing status', async () => {
      const photo = createCapturedPhoto('photo1');
      
      expect(queue.getStatus().processing).toBe(false);
      
      await queue.add(photo);
      
      // Check status during processing
      expect(queue.getStatus().processing).toBe(true);
      expect(queue.getStatus().currentItem).toBeTruthy();

      // Wait for completion
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(queue.getStatus().processing).toBe(false);
      expect(queue.getStatus().currentItem).toBeNull();
    });

    it('should update queue length correctly', async () => {
      const photos = Array.from({ length: 5 }, (_, i) => 
        createCapturedPhoto(`photo${i}`)
      );

      for (const photo of photos) {
        await queue.add(photo);
      }

      expect(queue.getQueueLength()).toBe(5);

      // Wait for some processing
      await new Promise(resolve => setTimeout(resolve, 200));

      expect(queue.getQueueLength()).toBeLessThan(5);
    });
  });

  describe('callbacks', () => {
    it('should call onProgress with correct data', async () => {
      const photo = createCapturedPhoto('photo1');
      await queue.add(photo);

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnProgress).toHaveBeenCalledWith(
        expect.objectContaining({
          current: 1,
          total: 1,
          photo: expect.objectContaining({
            image: photo.image,
          }),
        })
      );
    });

    it('should call onComplete with saved photo data', async () => {
      const photo = createCapturedPhoto('photo1');
      await queue.add(photo);

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnComplete).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'mocked-photo-id',
          filename: 'mocked-photo.jpg',
        }),
        expect.objectContaining({
          image: photo.image,
        })
      );
    });

    it('should provide correct progress for multiple items', async () => {
      const photos = Array.from({ length: 3 }, (_, i) => 
        createCapturedPhoto(`photo${i}`)
      );

      for (const photo of photos) {
        await queue.add(photo);
      }

      await new Promise(resolve => setTimeout(resolve, 200));

      // Check that progress was called with correct current/total values
      const progressCalls = mockOnProgress.mock.calls;
      expect(progressCalls.some(call => call[0].current === 1 && call[0].total === 3)).toBe(true);
      expect(progressCalls.some(call => call[0].current === 2 && call[0].total === 3)).toBe(true);
      expect(progressCalls.some(call => call[0].current === 3 && call[0].total === 3)).toBe(true);
    });
  });

  describe('edge cases', () => {
    it('should handle empty file objects', async () => {
      const photo: CapturedPhotoData = {
        image: new File([], 'empty.jpg', { type: 'image/jpeg' }),
        location: {
          latitude: 50.0617,
          longitude: 14.5146,
          accuracy: 10,
        },
        timestamp: Date.now(),
      };

      await queue.add(photo);
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnComplete).toHaveBeenCalled();
    });

    it('should handle missing optional fields', async () => {
      const photo: CapturedPhotoData = {
        image: new File(['test'], 'minimal.jpg', { type: 'image/jpeg' }),
        location: {
          latitude: 50.0617,
          longitude: 14.5146,
          accuracy: 10,
        },
        timestamp: Date.now(),
        // No bearing, no altitude
      };

      await queue.add(photo);
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(mockOnComplete).toHaveBeenCalled();
    });

    it('should handle rapid additions and removals', async () => {
      const addPromises = [];
      
      // Rapidly add many items
      for (let i = 0; i < 20; i++) {
        addPromises.push(queue.add(createCapturedPhoto(`photo${i}`)));
      }

      await Promise.all(addPromises);
      
      // Should have queued all items
      expect(queue.getQueueLength()).toBeGreaterThan(0);
      
      // Wait for processing to complete
      await new Promise(resolve => setTimeout(resolve, 500));
      
      expect(queue.getQueueLength()).toBe(0);
      expect(queue.getStatus().processedCount).toBeGreaterThan(0);
    });
  });
});