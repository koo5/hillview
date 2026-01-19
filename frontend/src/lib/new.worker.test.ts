/**
 * Integration tests for the new worker architecture
 * Tests by importing the worker module directly and calling handleMessage
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { PhotoData, SourceConfig } from './photoWorkerTypes';

// Track worker reference for auth responses
let workerRef: typeof import('./new.worker') | null = null;

// Mock the worker globals before importing
const mockPostMessage = vi.fn().mockImplementation((message: any) => {
  // Auto-respond to auth token requests
  if (message?.type === 'getAuthToken' && workerRef) {
    // Send auth token response back to worker
    queueMicrotask(() => {
      workerRef!.handleMessage({
        type: 'authToken',
        token: 'test-auth-token-12345'
      });
    });
  }
});
const mockSelf = {
  onmessage: null,
  postMessage: mockPostMessage
};

// Mock global worker environment
(globalThis as any).self = mockSelf;
(globalThis as any).postMessage = mockPostMessage;

// Mock __WORKER_VERSION__ for tests
(globalThis as any).__WORKER_VERSION__ = 'test-version-' + Date.now();

// No longer need fetch mock since we're using EventSource

// Mock EventSource for streaming tests
const mockEventSourceInstances = new Map<string, any>();
// Track close() calls for cancellation testing
const mockEventSourceCloseCalls: string[] = [];

interface MockEventSourceInstance {
  url: string;
  readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close: () => void;
  addEventListener: (type: string, listener: any) => void;
  removeEventListener: (type: string, listener: any) => void;
  dispatchEvent: (event: Event) => boolean;
}

const MockEventSource = vi.fn().mockImplementation((url: string): MockEventSourceInstance => {
  const instance: MockEventSourceInstance = {
    url,
    readyState: 1, // OPEN
    onopen: null,
    onmessage: null,
    onerror: null,
    close: vi.fn(() => {
      // Track which source was closed for cancellation testing
      const sourceMatch = url.match(/example\.com\/([^?]+)/);
      if (sourceMatch) {
        mockEventSourceCloseCalls.push(sourceMatch[1]);
      }
    }),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  };

  mockEventSourceInstances.set(url, instance);

  // Use queueMicrotask for test-friendly async handling
  queueMicrotask(() => {
    if (instance.onopen) {
      instance.onopen(new Event('open'));
    }

    // Send test data based on URL
    let testData: any[] = [];
    if (url.includes('source1')) {
      testData = testPhotosSource1;
    } else if (url.includes('source2')) {
      testData = testPhotosSource2;
    } else if (url.includes('bulk-source') || url.includes('city-photos')) {
      const count = url.includes('city-photos') ? 500 : 1000;
      testData = [];
      for (let i = 0; i < count; i++) {
        const lat = 50.0 + (i % 20) * 0.01;
        const lng = 10.0 + Math.floor(i / 20) * 0.01;
        testData.push(createTestPhoto(`${url.includes('city-photos') ? 'city' : 'bulk'}${i}`, lat, lng, i % 360));
      }
    } else if (url.includes('bearing-test')) {
      // Deliberately UNSORTED bearings to verify sorting actually works
      testData = [
        createTestPhoto('bearing1', 50.1, 10.1, 270),  // out of order
        createTestPhoto('bearing2', 50.1, 10.1, 45),   // out of order
        createTestPhoto('bearing3', 50.1, 10.1, 180),  // out of order
        createTestPhoto('bearing4', 50.1, 10.1, 0),    // out of order
        createTestPhoto('bearing5', 50.1, 10.1, 90)    // out of order
      ];
    } else if (url.includes('range-test')) {
      testData = [
        createTestPhoto('range1', 50.1, 10.1, 45),
        createTestPhoto('range2', 50.1, 10.1, 135)
      ];
    } else if (url.includes('distance-test')) {
      // Photos at specific distances from center (50.1, 10.1)
      // ~111m per 0.001 degree latitude at this location
      testData = [
        createTestPhoto('close1', 50.1005, 10.1005, 0),   // ~70m from center
        createTestPhoto('close2', 50.1008, 10.1, 90),     // ~90m from center
        createTestPhoto('far1', 50.12, 10.1, 180),        // ~2.2km from center
        createTestPhoto('far2', 50.1, 10.15, 270)         // ~3.5km from center
      ];
    }

    // Send photos as stream message (type must be 'photos' to match StreamSourceLoader)
    if (testData.length > 0 && instance.onmessage) {
      instance.onmessage(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'photos',
          photos: testData
        })
      }));
    }

    // Send completion message
    if (instance.onmessage) {
      instance.onmessage(new MessageEvent('message', {
        data: JSON.stringify({
          type: 'stream_complete'
        })
      }));
    }
  });

  return instance;
});

// Add EventSource static properties
Object.assign(MockEventSource, {
  CONNECTING: 0,
  OPEN: 1,
  CLOSED: 2,
  prototype: {}
});

global.EventSource = MockEventSource as any;

// Keep console logging for debugging infinite loop
const originalConsole = console.log;
beforeEach(() => {
  // Don't mock console.log for debugging
  // console.log = vi.fn();
  mockPostMessage.mockClear();
  MockEventSource.mockClear();
  mockEventSourceInstances.clear();
});

afterEach(() => {
  console.log = originalConsole;
});

// Test data
const createTestPhoto = (id: string, lat: number, lng: number, bearing: number = 0): PhotoData => ({
  id,
  uid: `test-${id}`,
  source_type: 'test',
  file: `${id}.jpg`,
  url: `https://example.com/${id}.jpg`,
  coord: { lat, lng },
  bearing,
  altitude: 0
});

const createTestBounds = (north: number, south: number, west: number, east: number) => ({
  top_left: { lat: north, lng: west },
  bottom_right: { lat: south, lng: east }
});

const createStreamSource = (id: string, enabled: boolean = true): SourceConfig => ({
  id,
  name: `Test ${id}`,
  type: 'stream',
  enabled,
  url: `https://example.com/${id}`,
  color: '#ff0000'
});

// Mock photo data
const testPhotosSource1 = [
  createTestPhoto('photo1', 50.1, 10.1, 0),
  createTestPhoto('photo2', 50.2, 10.2, 90),
  createTestPhoto('photo3', 50.3, 10.3, 180)
];

const testPhotosSource2 = [
  createTestPhoto('photo4', 50.15, 10.15, 45),
  createTestPhoto('photo5', 50.25, 10.25, 135)
];

describe('New Worker Integration Tests', () => {
  let messageId = 1;
  let worker: typeof import('./new.worker');

  beforeEach(async () => {
    // Reset message ID counter
    messageId = 1;

    // Clear the module cache to get a fresh worker instance with clean state
    vi.resetModules();

    // Re-mock globals after module reset (they get cleared too)
    (globalThis as any).self = {
      onmessage: null,
      postMessage: mockPostMessage
    };
    (globalThis as any).postMessage = mockPostMessage;
    (globalThis as any).__WORKER_VERSION__ = 'test-version-' + Date.now();

    // Set EventSource on both global and globalThis for Node.js compatibility
    (globalThis as any).EventSource = MockEventSource;
    (global as any).EventSource = MockEventSource;

    // Clear mock state
    mockPostMessage.mockClear();
    MockEventSource.mockClear();
    mockEventSourceInstances.clear();
    mockEventSourceCloseCalls.length = 0;  // Clear close() tracking

    // Dynamically import the worker after setting up mocks
    worker = await import('./new.worker');
    workerRef = worker;  // Set reference for auth token responses
  });

  const sendMessage = async (type: string, data: any): Promise<any> => {
    const id = messageId++;

    // Send message to worker
    worker.handleMessage({
      frontendMessageId: `frontend_${id}`,
      type,
      data,
      id
    });

    // Wait for processing to complete
    await waitForPhotosUpdate();

    // Return the last postMessage call that contains photosUpdate
    const photosUpdateCalls = mockPostMessage.mock.calls
      .filter(call => call[0]?.type === 'photosUpdate');

    if (photosUpdateCalls.length > 0) {
      return photosUpdateCalls[photosUpdateCalls.length - 1][0];
    }

    throw new Error('No photosUpdate received');
  };

  const waitForPhotosUpdate = async (timeout = 5000): Promise<void> => {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
      // Check if we got a photosUpdate message
      const hasPhotosUpdate = mockPostMessage.mock.calls
        .some(call => call[0]?.type === 'photosUpdate');

      if (hasPhotosUpdate) {
        // Give the internal queue time to process completion messages
        await new Promise(resolve => setTimeout(resolve, 50));
        return;
      }

      // Wait a bit before checking again
      await new Promise(resolve => setTimeout(resolve, 10));
    }

    throw new Error('Timeout waiting for photosUpdate');
  };

  it('should handle config updates with stream sources', async () => {
    const sources = [
      createStreamSource('source1'),
      createStreamSource('source2')
    ];

    // Send config update with proper version check
    await sendMessage('configUpdated', {
      config: {
        sources,
        expectedWorkerVersion: (globalThis as any).__WORKER_VERSION__
      }
    });

    // Clear previous postMessage calls
    mockPostMessage.mockClear();

    // Then send area update to trigger photo filtering and return
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4); // Covers all test photos
    const response = await sendMessage('areaUpdated', {
      area: bounds
    });

    expect(response.type).toBe('photosUpdate');
    expect(response.photos_in_area).toBeDefined();
    expect(response.photos_in_range).toBeDefined();
    expect(response.photos_in_area.length).toBeGreaterThan(0);

    // Should have photos from both sources
    const photoIds = response.photos_in_area.map((p: PhotoData) => p.id);
    expect(photoIds).toContain('photo1');
    expect(photoIds).toContain('photo4');
  });

  it('should handle area updates with range', async () => {
    // First send config
    const sources = [createStreamSource('source1')];
    await sendMessage('configUpdated', {
      config: { sources }
    });

    // Clear previous postMessage calls
    mockPostMessage.mockClear();

    // Then send area update
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4);
    const response = await sendMessage('areaUpdated', {
      area: bounds,
      range: 5000 // 5km range
    });

    expect(response.type).toBe('photosUpdate');
    expect(response.current_range).toBe(5000);
    expect(response.photos_in_area.length).toBeGreaterThan(0);

    // Photos should be within the area bounds
    response.photos_in_area.forEach((photo: PhotoData) => {
      expect(photo.coord.lat).toBeGreaterThanOrEqual(bounds.bottom_right.lat);
      expect(photo.coord.lat).toBeLessThanOrEqual(bounds.top_left.lat);
      expect(photo.coord.lng).toBeGreaterThanOrEqual(bounds.top_left.lng);
      expect(photo.coord.lng).toBeLessThanOrEqual(bounds.bottom_right.lng);
    });
  });

  it('should apply smart culling for many photos', async () => {
    // MockEventSource creates 1000 bulk photos spread across a grid
    // lat = 50.0 + (i % 20) * 0.01, lng = 10.0 + floor(i/20) * 0.01
    const sources = [createStreamSource('bulk-source')];

    await sendMessage('configUpdated', {
      config: { sources }
    });

    mockPostMessage.mockClear();

    // Area update triggers photo loading
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4);
    const response = await sendMessage('areaUpdated', {
      area: bounds
    });

    // Verify culling actually reduced the count (1000 sent, fewer returned)
    expect(response.photos_in_area.length).toBeLessThan(1000);
    expect(response.photos_in_area.length).toBeLessThanOrEqual(700); // MAX_PHOTOS_IN_AREA
    expect(response.photos_in_area.length).toBeGreaterThan(0);
    expect(response.photos_in_range.length).toBeLessThanOrEqual(200); // MAX_PHOTOS_IN_RANGE

    // Verify spatial distribution: culled photos should come from different grid cells
    // not just the first N photos. Check that we have photos from multiple lat buckets.
    const latBuckets = new Set(
      response.photos_in_area.map((p: PhotoData) => Math.floor(p.coord.lat * 100))
    );
    // Should have photos from multiple distinct latitude bands (grid-based culling)
    expect(latBuckets.size).toBeGreaterThan(5);
  });

  it('should sort photosInRange by bearing', async () => {
    // MockEventSource sends bearing-test photos with UNSORTED bearings: 270, 45, 180, 0, 90
    // This verifies the worker actually sorts them, not just returns pre-sorted data
    const sources = [createStreamSource('bearing-test')];
    await sendMessage('configUpdated', {
      config: { sources }
    });

    mockPostMessage.mockClear();

    // Area update triggers photo loading
    const bounds = createTestBounds(50.2, 50.0, 10.0, 10.2);
    const response = await sendMessage('areaUpdated', {
      area: bounds,
      range: 5000
    });

    // photosInRange should be sorted by bearing ascending
    const bearings = response.photos_in_range.map((p: PhotoData) => p.bearing);

    // Verify we got multiple photos with different bearings
    expect(bearings.length).toBeGreaterThan(1);

    // Verify they are sorted (input was 270, 45, 180, 0, 90 - should become 0, 45, 90, 180, 270)
    const expectedSorted = [...bearings].sort((a, b) => a - b);
    expect(bearings).toEqual(expectedSorted);
  });

  it('should handle disabled sources', async () => {
    const sources = [
      createStreamSource('source1', true),   // enabled - uses testPhotosSource1
      createStreamSource('disabled', false)  // disabled
    ];

    // Config only sets up sources, doesn't load photos
    await sendMessage('configUpdated', {
      config: { sources }
    });

    mockPostMessage.mockClear();

    // Area update triggers actual photo loading
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4);
    const response = await sendMessage('areaUpdated', {
      area: bounds
    });

    expect(response.type).toBe('photosUpdate');

    // Should only have photos from enabled source
    const photoIds = response.photos_in_area.map((p: PhotoData) => p.id);
    expect(photoIds).toContain('photo1'); // From enabled source (source1)
    expect(MockEventSource).toHaveBeenCalledTimes(1); // Only called for enabled source
  });

  it('should filter photos by actual distance from map center', async () => {
    // distance-test has photos at known distances from center (50.1, 10.1):
    // - close1: ~70m, close2: ~90m, far1: ~2.2km, far2: ~3.5km
    const sources = [createStreamSource('distance-test')];
    // Bounds centered on (50.1, 10.1)
    const bounds = createTestBounds(50.2, 50.0, 10.0, 10.2);

    await sendMessage('configUpdated', {
      config: { sources }
    });

    mockPostMessage.mockClear();

    // Small range (200m) should only include close photos
    const response1 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 200
    });

    expect(response1.photos_in_range).toBeDefined();
    const smallRangeIds = response1.photos_in_range.map((p: PhotoData) => p.id);
    // Should include close1 (~70m) and close2 (~90m)
    expect(smallRangeIds).toContain('close1');
    expect(smallRangeIds).toContain('close2');
    // Should NOT include far photos
    expect(smallRangeIds).not.toContain('far1');
    expect(smallRangeIds).not.toContain('far2');

    mockPostMessage.mockClear();

    // Large range (5000m) should include all photos
    const response2 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 5000
    });

    expect(response2.photos_in_range).toBeDefined();
    const largeRangeIds = response2.photos_in_range.map((p: PhotoData) => p.id);
    // Should include all photos
    expect(largeRangeIds).toContain('close1');
    expect(largeRangeIds).toContain('close2');
    expect(largeRangeIds).toContain('far1');
    expect(largeRangeIds).toContain('far2');

    // Larger range includes more photos
    expect(largeRangeIds.length).toBeGreaterThan(smallRangeIds.length);
  });

  it('should handle rapid area updates like real-world map panning', async () => {
    // Set up multiple sources with realistic photo distributions
    const sources = [
      createStreamSource('city-photos'),    // Will have 1000 photos (bulk data)
      createStreamSource('source1'),        // Will have 3 photos (existing test data)
      createStreamSource('source2')         // Will have 2 photos (existing test data)
    ];

    // Initial config
    await sendMessage('configUpdated', {
      config: { sources }
    });

    // Simulate rapid area updates as user pans across a city
    const areas = [
      // Start in city center (covers existing test photos)
      { bounds: createTestBounds(50.3, 49.9, 9.9, 10.3), name: 'city-center' },
      // Pan north
      { bounds: createTestBounds(50.4, 50.0, 9.9, 10.3), name: 'north-district' },
      // Pan east (covers bulk photos from mock)
      { bounds: createTestBounds(50.5, 50.1, 10.0, 10.4), name: 'east-district' },
      // Zoom out (larger area covering more photos)
      { bounds: createTestBounds(50.6, 49.8, 9.8, 10.6), name: 'wide-view' },
      // Zoom in on specific area with known photos
      { bounds: createTestBounds(50.15, 50.05, 9.95, 10.25), name: 'detailed-view' }
    ];

    const responses: any[] = [];

    for (const area of areas) {
      mockPostMessage.mockClear();

      const response = await sendMessage('areaUpdated', {
        area: area.bounds,
        range: 1500 // 1.5km range
      });

      responses.push({ ...response, areaName: area.name });

      // Verify each response
      expect(response.type).toBe('photosUpdate');
      expect(response.photos_in_area).toBeDefined();
      expect(response.photos_in_range).toBeDefined();
      expect(response.current_range).toBe(1500);
    }

    // Verify we got responses for all areas
    expect(responses).toHaveLength(5);

    // Should handle all requests without errors
    expect(responses.every(r => r.type === 'photosUpdate')).toBe(true);
  });

  it('should handle overlapping area updates gracefully', async () => {
    // Test rapid-fire area updates without waiting between them
    const sources = [createStreamSource('source1'), createStreamSource('source2')];
    await sendMessage('configUpdated', {
      config: { sources }
    });

    // Clear setup calls
    mockPostMessage.mockClear();

    // Send multiple area updates rapidly (simulating fast map panning)
    const updatePromises = [];
    for (let i = 0; i < 5; i++) {
      const offset = i * 0.02; // Small incremental moves
      const bounds = createTestBounds(50.1 + offset, 49.9 + offset, 9.9 + offset, 10.1 + offset);

      updatePromises.push(sendMessage('areaUpdated', {
        area: bounds,
        range: 1000
      }));
    }

    // Wait for all to complete - this tests that the worker handles overlapping processes
    const responses = await Promise.all(updatePromises);

    // All should complete successfully
    responses.forEach((response) => {
      expect(response.type).toBe('photosUpdate');
      expect(response.photos_in_area).toBeDefined();
      expect(response.photos_in_range).toBeDefined();
      expect(response.current_range).toBe(1000);
    });

    // Should have processed all requests
    expect(responses).toHaveLength(5);

    // Test that worker can handle rapid consecutive updates without breaking
    expect(responses.every(r => typeof r.photos_in_area.length === 'number')).toBe(true);
  });

  it('should handle worker version validation correctly', async () => {
    const sources = [createStreamSource('source1')];

    // Test with correct version - should work
    const response = await sendMessage('configUpdated', {
      config: {
        sources,
        expectedWorkerVersion: (globalThis as any).__WORKER_VERSION__
      }
    });

    // Verify correct version produces a valid response
    expect(response.type).toBe('photosUpdate');

    // Clear messages and test with wrong version
    mockPostMessage.mockClear();

    // Capture the expected version mismatch error
    let caughtError: Error | null = null;
    const errorHandler = (error: Error) => {
      if (error.message.includes('Worker version mismatch')) {
        caughtError = error;
      }
    };
    process.on('unhandledRejection', errorHandler);

    try {
      // Send message with wrong version - processConfig will throw but the error
      // happens asynchronously (processConfig is not awaited in the worker).
      worker.handleMessage({
        frontendMessageId: 'frontend_version_test',
        type: 'configUpdated',
        data: {
          config: {
            sources,
            expectedWorkerVersion: 'wrong-version-123'
          }
        },
        id: 999
      });

      // Wait a short time for the async error to occur
      await new Promise(resolve => setTimeout(resolve, 200));

      // Verify NO photosUpdate was sent for the invalid version
      const photosUpdateCalls = mockPostMessage.mock.calls
        .filter(call => call[0]?.type === 'photosUpdate');

      expect(photosUpdateCalls.length).toBe(0);

      // Verify the version mismatch error was thrown
      expect(caughtError).not.toBeNull();
      expect(caughtError!.message).toContain('Worker version mismatch');
    } finally {
      process.removeListener('unhandledRejection', errorHandler);
    }
  });

  it('should exclude data from removed sources after config change', async () => {
    // Start with both sources
    await sendMessage('configUpdated', {
      config: { sources: [createStreamSource('source1'), createStreamSource('source2')] }
    });

    // Trigger loading from both sources
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4);
    const response1 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 1000
    });

    // Verify we have photos from BOTH sources
    const photoIds1 = response1.photos_in_area.map((p: PhotoData) => p.id);
    expect(photoIds1).toContain('photo1'); // From source1
    expect(photoIds1).toContain('photo4'); // From source2

    mockPostMessage.mockClear();

    // Change config to ONLY source2 (removes source1)
    await sendMessage('configUpdated', {
      config: { sources: [createStreamSource('source2')] }
    });

    // Trigger new area update
    mockPostMessage.mockClear();
    const response2 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 1000
    });

    // Result should ONLY contain photos from source2 (source1 was removed)
    const photoIds2 = response2.photos_in_area.map((p: PhotoData) => p.id);
    expect(photoIds2).toContain('photo4'); // From source2
    expect(photoIds2).toContain('photo5'); // From source2
    // source1 photos should NOT be in the result - source was removed
    expect(photoIds2).not.toContain('photo1');
    expect(photoIds2).not.toContain('photo2');
    expect(photoIds2).not.toContain('photo3');
  });
});
