/**
 * Shared utilities for managing test users across Playwright tests
 */

import { BACKEND_URL } from './adminAuth';

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
  const response = await fetch(`${BACKEND_URL}/api/debug/clear-database`, {
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
export async function recreateTestUsers(): Promise<TestUserSetupResult> {
  const response = await fetch(`${BACKEND_URL}/api/debug/recreate-test-users`, {
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
 * Individual tests should call recreateTestUsers() as needed
 */
export async function setupCleanTestEnvironment(): Promise<void> {
  await clearDatabase();
}

/**
 * Login as any user by username and password.
 */
export async function loginAs(page: any, username: string, password: string) {
  await page.goto('/login');

  // Wait for the app's JS bundle to finish loading before interacting. On WebKit
  // (prod build, code-split chunks) the submit handler may not be wired until the
  // bundle settles, so clicking too early silently no-ops and login never
  // navigates. networkidle is reliable here — the login page is simple (no map,
  // no SSE stream), so it settles quickly and doesn't hang like the map pages do.
  await page.waitForLoadState('networkidle');

  // networkidle can resolve before the DOM is painted on WebKit, so also wait for
  // the form itself with an actionable timeout.
  await page.getByTestId('login-username-input').waitFor({ state: 'visible', timeout: 11*15000 });

  await page.getByTestId('login-username-input').fill(username);
  await page.getByTestId('login-password-input').fill(password);
  await page.getByTestId('login-submit-button').click();

  // Wait for successful login redirect
  await page.waitForURL('/', { timeout: 11*15000 });
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
  await page.waitForURL('/login', { timeout: 11*15000 });
}
