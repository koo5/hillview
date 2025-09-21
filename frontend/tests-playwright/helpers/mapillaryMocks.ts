/**
 * Shared utilities for mocking Mapillary data across Playwright tests
 */

export interface MockMapillaryPhoto {
  id: string;
  geometry: {
    type: "Point";
    coordinates: [number, number];
  };
  compass_angle: number;
  computed_compass_angle: number;
  computed_rotation: number;
  computed_altitude?: number;
  captured_at: string;
  is_pano: boolean;
  thumb_1024_url: string;
  creator: {
    username: string;
    id: string;
  };
  sequence_id?: string;
  organization_id?: string;
}

export interface MockMapillaryData {
  data: MockMapillaryPhoto[];
}

/**
 * Create mock Mapillary data with photos distributed around a center point
 */
export function createMockMapillaryData(
  centerLat = 50.0755,
  centerLng = 14.4378,
  photoCount = 15
): MockMapillaryData {
  const baseLatitude = centerLat;
  const baseLongitude = centerLng;
  const photos: MockMapillaryPhoto[] = [];

  for (let i = 1; i <= photoCount; i++) {
    // Distribute photos very close to center to ensure they're within bbox
    const angle = (i * 24) % 360; // Distribute in a circle
    const distance = 0.0001 * ((i % 3) + 1); // Very small distances (0.0001, 0.0002, 0.0003 degrees)
    const latOffset = distance * Math.sin(angle * Math.PI / 180);
    const lngOffset = distance * Math.cos(angle * Math.PI / 180);

    photos.push({
      id: `mock_mapillary_${i.toString().padStart(3, '0')}`,
      geometry: {
        type: "Point",
        coordinates: [baseLongitude + lngOffset, baseLatitude + latOffset]
      },
      compass_angle: (i * 24) % 360, // Vary angles
      computed_compass_angle: (i * 24) % 360,
      computed_rotation: 0.0,
      computed_altitude: 200.0 + (i * 10),
      captured_at: `2024-01-15T${String(10 + (i % 12)).padStart(2, '0')}:30:00Z`,
      is_pano: false,
      thumb_1024_url: `https://mock.mapillary.com/thumb${i.toString().padStart(3, '0')}.jpg`,
      creator: {
        username: `mock_creator_${((i - 1) % 3) + 1}`,
        id: `mock_creator_${((i - 1) % 3) + 1}`
      },
      sequence_id: `mock_sequence_${Math.floor((i - 1) / 5) + 1}`, // Group into sequences of 5
      organization_id: "mock_org_001"
    });
  }

  return { data: photos };
}

/**
 * Set mock Mapillary data via backend debug endpoint
 */
export async function setMockMapillaryData(page: any, mockData: MockMapillaryData) {
  const response = await page.request.post('http://localhost:8055/api/debug/mock-mapillary', {
    data: mockData
  });

  if (response.status() !== 200) {
    throw new Error(`Failed to set mock data: ${response.status()}`);
  }

  const result = await response.json();
  console.log(`✓ Set mock Mapillary data: ${result.details.photos_count} photos`);
  return result;
}

/**
 * Clear mock Mapillary data
 */
export async function clearMockMapillaryData(page: any) {
  try {
    // Clear mock data
    const mockResponse = await page.request.delete('http://localhost:8055/api/debug/mock-mapillary');
    if (mockResponse.status() === 200) {
      console.log('✓ Cleared mock Mapillary data');
    }

    // Clear database/cache to force fresh requests
    const cacheResponse = await page.request.post('http://localhost:8055/api/debug/clear-database');
    if (cacheResponse.status() === 200) {
      console.log('✓ Cleared database/cache');
    }
  } catch (e) {
    console.log('⚠ Could not clear data:', (e as Error).message);
  }
}

/**
 * Complete setup: set mock data, clear database cache, reload page
 * Use this for tests that need fresh Mapillary data
 */
export async function setupMockMapillaryData(page: any, mockData: MockMapillaryData) {
  // Set mock data (overwrites any existing mock data)
  await setMockMapillaryData(page, mockData);

  // Clear database/cache to remove any cached data (prevents cache+live duplication)
  const cacheResponse = await page.request.post('http://localhost:8055/api/debug/clear-database');
  if (cacheResponse.status() === 200) {
    console.log('✓ Cleared database/cache');
  }

  // Reload page so frontend fetches the new mocked data
  await page.reload();
  await page.waitForLoadState('networkidle');
}

/**
 * Quick setup with default Prague data for most tests
 */
export async function setupDefaultMockMapillaryData(page: any) {
  const mockData = createMockMapillaryData();
  await setupMockMapillaryData(page, mockData);
  return mockData;
}