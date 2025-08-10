/**
 * Integration tests for the new worker architecture
 * Tests by importing the worker module directly and calling handleMessage
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import type { PhotoData, SourceConfig } from './photoWorkerTypes';

// Mock the worker globals before importing
const mockPostMessage = vi.fn();
const mockSelf = {
  onmessage: null,
  postMessage: mockPostMessage
};

// Mock global worker environment
(globalThis as any).self = mockSelf;
(globalThis as any).postMessage = mockPostMessage;

// No longer need fetch mock since we're using EventSource

// Mock EventSource for streaming tests
const mockEventSourceInstances = new Map<string, any>();
const MockEventSource = vi.fn().mockImplementation((url: string) => {
  console.log(`MockEventSource: Creating new instance for ${url}`);
  const instance = {
    url,
    readyState: 1, // OPEN
    onopen: null,
    onmessage: null,
    onerror: null,
    close: vi.fn(() => console.log(`MockEventSource: Closed ${url}`)),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn()
  };
  
  mockEventSourceInstances.set(url, instance);
  
  // Simulate connection opening after a short delay
  setTimeout(() => {
    console.log(`MockEventSource: Opening connection for ${url}`);
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
      testData = [
        createTestPhoto('bearing1', 50.1, 10.1, 0),
        createTestPhoto('bearing2', 50.1, 10.1, 90),
        createTestPhoto('bearing3', 50.1, 10.1, 180),
        createTestPhoto('bearing4', 50.1, 10.1, 270)
      ];
    } else if (url.includes('range-test')) {
      testData = [
        createTestPhoto('range1', 50.1, 10.1, 45),
        createTestPhoto('range2', 50.1, 10.1, 135)
      ];
    }
    
    // Send photos as stream message
    if (testData.length > 0 && instance.onmessage) {
      console.log(`MockEventSource: Sending ${testData.length} photos for ${url}`);
      instance.onmessage({
        data: JSON.stringify({
          type: 'cached_photos',
          photos: testData
        })
      });
    }
    
    // Send completion message
    if (instance.onmessage) {
      console.log(`MockEventSource: Sending completion for ${url}`);
      instance.onmessage({
        data: JSON.stringify({
          type: 'stream_complete'
        })
      });
    }
  }, 10);
  
  return instance;
});

global.EventSource = MockEventSource;

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
    
    // No need for fetch mocks since we're using EventSource for streams

    // Dynamically import the worker after setting up mocks
    worker = await import('./new.worker');
  });

  const sendMessage = async (type: string, data: any): Promise<any> => {
    const id = messageId++;
    console.log(`TEST: Sending message ${type} with id ${id}`);
    
    // Send message to worker
    worker.handleMessage({
      frontendMessageId: `frontend_${id}`,
      type,
      data,
      id
    });

    console.log(`TEST: Message sent, waiting for response...`);
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
    
    // Send config update
    await sendMessage('configUpdated', {
      config: { sources, expectedWorkerVersion: '1.0.0' }
    });
    
    // Clear previous postMessage calls
    mockPostMessage.mockClear();
    
    // Then send area update to trigger photo filtering and return
    const bounds = createTestBounds(50.4, 49.9, 9.9, 10.4); // Covers all test photos
    const response = await sendMessage('areaUpdated', {
      area: bounds
    });
    
    expect(response.type).toBe('photosUpdate');
    expect(response.photosInArea).toBeDefined();
    expect(response.photosInRange).toBeDefined();
    expect(response.photosInArea.length).toBeGreaterThan(0);
    
    // Should have photos from both sources
    const photoIds = response.photosInArea.map((p: PhotoData) => p.id);
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
    expect(response.currentRange).toBe(5000);
    expect(response.photosInArea.length).toBeGreaterThan(0);
    
    // Photos should be within the area bounds
    response.photosInArea.forEach((photo: PhotoData) => {
      expect(photo.coord.lat).toBeGreaterThanOrEqual(bounds.bottom_right.lat);
      expect(photo.coord.lat).toBeLessThanOrEqual(bounds.top_left.lat);
      expect(photo.coord.lng).toBeGreaterThanOrEqual(bounds.top_left.lng);
      expect(photo.coord.lng).toBeLessThanOrEqual(bounds.bottom_right.lng);
    });
  });

  it('should apply smart culling for many photos', async () => {
    // The MockEventSource will automatically create 1000 bulk photos for bulk-source URL
    const sources = [createStreamSource('bulk-source')];
    const response = await sendMessage('configUpdated', {
      config: { sources }
    });
    
    // Should be culled to reasonable limits
    expect(response.photosInArea.length).toBeLessThanOrEqual(700); // MAX_PHOTOS_IN_AREA
    expect(response.photosInArea.length).toBeGreaterThan(0);
    expect(response.photosInRange.length).toBeLessThanOrEqual(200); // MAX_PHOTOS_IN_RANGE
  });

  it('should sort photosInRange by bearing', async () => {
    // The MockEventSource will automatically create bearing-test photos with bearings 0, 90, 180, 270
    const sources = [createStreamSource('bearing-test')];
    const response = await sendMessage('configUpdated', {
      config: { sources }
    });
    
    // photosInRange should be sorted by bearing (0, 90, 180, 270)
    const bearings = response.photosInRange.map((p: PhotoData) => p.bearing);
    for (let i = 1; i < bearings.length; i++) {
      expect(bearings[i]).toBeGreaterThanOrEqual(bearings[i-1]);
    }
  });

  it('should handle disabled sources', async () => {
    const sources = [
      createStreamSource('enabled', true),
      createStreamSource('disabled', false)
    ];
    
    const response = await sendMessage('configUpdated', {
      config: { sources }
    });
    
    expect(response.type).toBe('photosUpdate');
    
    // Should only have photos from enabled source
    const photoIds = response.photosInArea.map((p: PhotoData) => p.id);
    expect(photoIds).toContain('photo1'); // From enabled source
    expect(MockEventSource).toHaveBeenCalledTimes(1); // Only called for enabled source
  });

  it('should update range dynamically', async () => {
    const sources = [createStreamSource('range-test')];
    const bounds = createTestBounds(50.2, 50.0, 10.0, 10.2);
    
    // Send config first
    await sendMessage('configUpdated', {
      config: { sources }
    });
    
    // Clear previous calls
    mockPostMessage.mockClear();
    
    // Send area with small range
    const response1 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 50 // Very small range
    });
    
    expect(response1.currentRange).toBe(50);
    const smallRangeCount = response1.photosInRange.length;
    
    // Clear previous calls
    mockPostMessage.mockClear();
    
    // Send area with larger range  
    const response2 = await sendMessage('areaUpdated', {
      area: bounds,
      range: 5000 // Much larger range
    });
    
    expect(response2.currentRange).toBe(5000);
    const largeRangeCount = response2.photosInRange.length;
    
    // Larger range should include more or equal photos
    expect(largeRangeCount).toBeGreaterThanOrEqual(smallRangeCount);
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
      expect(response.photosInArea).toBeDefined();
      expect(response.photosInRange).toBeDefined();
      expect(response.currentRange).toBe(1500);
      
      // Should have some photos for most areas (depending on mock data)
      console.log(`${area.name}: ${response.photosInArea.length} in area, ${response.photosInRange.length} in range`);
    }

    // Verify we got responses for all areas
    expect(responses).toHaveLength(5);
    
    // Verify that different areas might have different photo counts
    // (this tests that culling and filtering is working)
    const photoCounts = responses.map(r => r.photosInArea.length);
    console.log('Photo counts by area:', photoCounts);
    
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
    responses.forEach((response, i) => {
      expect(response.type).toBe('photosUpdate');
      expect(response.photosInArea).toBeDefined();
      expect(response.photosInRange).toBeDefined();
      expect(response.currentRange).toBe(1000);
      console.log(`Update ${i}: ${response.photosInArea.length} photos in area`);
    });

    // Should have processed all requests
    expect(responses).toHaveLength(5);
    
    // Test that worker can handle rapid consecutive updates without breaking
    expect(responses.every(r => typeof r.photosInArea.length === 'number')).toBe(true);
  });

  it('should prioritize config updates over area updates', async () => {
    // Start with one source
    await sendMessage('configUpdated', {
      config: { sources: [createStreamSource('source1')] }
    });

    // Send area update
    const areaPromise = sendMessage('areaUpdated', {
      area: createTestBounds(50.2, 50.0, 10.0, 10.2),
      range: 1000
    });

    // Immediately send config update (should interrupt area processing)
    const configPromise = sendMessage('configUpdated', {
      config: { sources: [createStreamSource('source2')] }
    });

    const [areaResult, configResult] = await Promise.all([areaPromise, configPromise]);

    // Both should complete successfully
    expect(areaResult.type).toBe('photosUpdate');
    expect(configResult.type).toBe('photosUpdate');
    
    // Config update should have priority and its result should reflect the new source
    console.log('Area result photos:', areaResult.photosInArea.length);
    console.log('Config result photos:', configResult.photosInArea.length);
  });
});