/**
 * Backend cleanup utilities for Appium tests
 * Ensures clean database state before running Android tests
 */

export interface BackendCleanupResult {
  database_cleared: boolean;
  users_recreated: boolean;
  mapillary_mocked: boolean;
  test_user_password?: string;
  admin_user_password?: string;
}

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
 * Create mock Mapillary data around the Android test location
 * Using Prague coordinates (50.114430°, 14.523529°) from test runs
 */
function createMockMapillaryDataForAndroidTest(
  centerLat = 50.114430,
  centerLng = 14.523529,
  photoCount = 20
): MockMapillaryData {
  const photos: MockMapillaryPhoto[] = [];

  for (let i = 1; i <= photoCount; i++) {
    // Distribute photos in a circle around the test location
    const angle = (i * 18) % 360; // 20 photos = 18 degrees apart
    const distance = 0.0002 * ((i % 4) + 1); // Small distances around test location
    const latOffset = distance * Math.sin(angle * Math.PI / 180);
    const lngOffset = distance * Math.cos(angle * Math.PI / 180);

    photos.push({
      id: `android_test_mapillary_${i.toString().padStart(3, '0')}`,
      geometry: {
        type: "Point",
        coordinates: [centerLng + lngOffset, centerLat + latOffset]
      },
      compass_angle: (i * 18) % 360,
      computed_compass_angle: (i * 18) % 360,
      computed_rotation: 0.0,
      computed_altitude: 180.0 + (i * 5),
      captured_at: `2024-10-09T${String(8 + (i % 14)).padStart(2, '0')}:15:00Z`,
      is_pano: false,
      thumb_1024_url: `https://mock.mapillary.com/android_test_${i.toString().padStart(3, '0')}.jpg`,
      creator: {
        username: `android_test_creator_${((i - 1) % 4) + 1}`,
        id: `android_test_creator_${((i - 1) % 4) + 1}`
      },
      sequence_id: `android_test_sequence_${Math.floor((i - 1) / 5) + 1}`,
      organization_id: "android_test_org_001"
    });
  }

  return { data: photos };
}

/**
 * Clear the entire database and recreate test users
 * Should be called before each test to ensure clean state
 */
export async function cleanBackendState(): Promise<BackendCleanupResult> {
  // Backend cleanup runs from test runner (Node.js), so use localhost not Android emulator URL
  const backendUrl = process.env.VITE_BACKEND || 'http://localhost:8055/api';

  try {
    console.log('🢄🧹 Backend Cleanup: Starting database cleanup...');

    // Step 1: Clear database
    const clearResponse = await fetch(`${backendUrl}/debug/clear-database`, {
      method: 'POST'
    });

    if (!clearResponse.ok) {
      throw new Error(`Failed to clear database: ${clearResponse.status} ${clearResponse.statusText}`);
    }

    console.log('🢄🧹 Backend Cleanup: Database cleared successfully');

    // Step 2: Recreate test users
    const usersResponse = await fetch(`${backendUrl}/debug/recreate-test-users`, {
      method: 'POST'
    });

    if (!usersResponse.ok) {
      throw new Error(`Failed to recreate test users: ${usersResponse.status} ${usersResponse.statusText}`);
    }

    const usersResult = await usersResponse.json();
    console.log('🢄🧹 Backend Cleanup: Test users recreated:', usersResult);

    // Step 3: Set up mock Mapillary data around test location
    const mockMapillaryData = createMockMapillaryDataForAndroidTest();
    const mapillaryResponse = await fetch(`${backendUrl}/debug/mock-mapillary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mockMapillaryData)
    });

    if (!mapillaryResponse.ok) {
      throw new Error(`Failed to set mock Mapillary data: ${mapillaryResponse.status} ${mapillaryResponse.statusText}`);
    }

    const mapillaryResult = await mapillaryResponse.json();
    console.log('🢄🧹 Backend Cleanup: Mock Mapillary data set:', mapillaryResult.details?.photos_count, 'photos');

    const passwords = usersResult.details?.user_passwords;

    return {
      database_cleared: true,
      users_recreated: true,
      mapillary_mocked: true,
      test_user_password: passwords?.test,
      admin_user_password: passwords?.admin
    };

  } catch (error) {
    console.error('🢄🧹 Backend Cleanup: Failed to clean backend state:', error);
    throw error;
  }
}

/**
 * Check if backend is available and ready for testing
 */
export async function checkBackendHealth(): Promise<boolean> {
  // Health check runs from test runner (Node.js), so use localhost not Android emulator URL
  const backendUrl = process.env.VITE_BACKEND || 'http://localhost:8055/api';

  try {
    const response = await fetch(`${backendUrl}/debug`, {
      method: 'GET'
    });

    const isHealthy = response.ok;
    console.log(`🢄🧹 Backend Health Check: ${isHealthy ? 'HEALTHY' : 'UNHEALTHY'} (${response.status})`);
    return isHealthy;

  } catch (error) {
    console.error('🢄🧹 Backend Health Check: Failed to reach backend:', error);
    return false;
  }
}

/**
 * Wait for backend to be ready with retries
 */
export async function waitForBackend(maxRetries = 10, delayMs = 2000): Promise<void> {
  console.log('🢄🧹 Backend Wait: Waiting for backend to be ready...');

  for (let i = 0; i < maxRetries; i++) {
    if (await checkBackendHealth()) {
      console.log('🢄🧹 Backend Wait: Backend is ready!');
      return;
    }

    if (i < maxRetries - 1) {
      console.log(`🢄🧹 Backend Wait: Attempt ${i + 1}/${maxRetries} failed, retrying in ${delayMs}ms...`);
      await new Promise(resolve => setTimeout(resolve, delayMs));
    }
  }

  throw new Error(`Backend not ready after ${maxRetries} attempts`);
}