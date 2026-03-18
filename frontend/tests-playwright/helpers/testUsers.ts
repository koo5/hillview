/**
 * Shared utilities for managing test users across Playwright tests
 */

export interface TestUserCredentials {
  test: string;
  admin: string;
  testuser: string;
}

// Removed global cache - each test should be independent

export interface TestUserSetupResult {
  passwords: TestUserCredentials;
  users_created: string[];
  users_deleted: number;
}

/**
 * Clear the entire database - use with caution!
 */
export async function clearDatabase(): Promise<void> {
  const response = await fetch('http://localhost:8055/api/debug/clear-database', {
    method: 'POST'
  });

  if (!response.ok) {
    throw new Error(`Failed to clear database: ${response.status} ${response.statusText}`);
  }
}

/**
 * Create test users and return their credentials
 * Should be called after clearDatabase() for clean state
 */
export async function createTestUsers(): Promise<TestUserSetupResult> {
  const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
    method: 'POST'
  });

  if (!response.ok) {
    throw new Error(`Failed to create test users: ${response.status} ${response.statusText}`);
  }

  const result = await response.json();

  if (result.detail) {
    // Handle error responses
    throw new Error(`API error: ${result.detail}`);
  }

  const passwords = result.details?.user_passwords;
  if (!passwords?.test) {
    throw new Error(`Test user password not found in API response: ${JSON.stringify(result)}`);
  }

  return {
    passwords,
    users_created: result.details?.created_users || [],
    users_deleted: result.details?.users_deleted || 0
  };
}

/**
 * Clear database only - for global setup
 * Individual tests should call createTestUsers() as needed
 */
export async function setupCleanTestEnvironment(): Promise<void> {
  await clearDatabase();
}

/**
 * Login as any user by username and password.
 */
export async function loginAs(page: any, username: string, password: string) {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  await page.fill('input[type="text"]', username);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]');

  // Wait for successful login redirect
  await page.waitForURL('/', { timeout: 15000 });
}

/**
 * Login as test user with provided credentials
 */
export async function loginAsTestUser(page: any, password: string) {
  await loginAs(page, 'test', password);
}

/**
 * Logout the current user via the navigation menu.
 */
export async function logoutUser(page: any) {
  await page.getByLabel('Toggle menu').click();
  await page.locator('button:has-text("Logout")').click();
  await page.waitForURL('/login', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
}