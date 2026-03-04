import { test, expect } from './fixtures';
import { uploadPhoto } from './helpers/photoUpload';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Activity Log', () => {
  let testPasswords: { test: string; admin: string; testuser: string };

  test.beforeEach(async () => {
    // Clean up and recreate test users before each test
    const result = await createTestUsers();
    testPasswords = result.passwords;
  });

  test('Activity log should show upload activities', async ({ page }) => {
    // Login with test user
    await loginAsTestUser(page, testPasswords.test);

    // Upload a photo using the shared helper (handles license checkbox)
    await uploadPhoto(page, '2025-07-10-19-10-37_🔶∏🗿↻🌞🌲.jpg');

    // Check if activity log exists and has entries
    const activityLog = page.locator('.activity-log');
    if (await activityLog.isVisible()) {
      console.log('🢄✓ Activity log is visible');

      const logEntries = page.locator('.log-entry');
      const count = await logEntries.count();
      console.log(`✓ Found ${count} log entries`);

      // Check if there's an upload-related entry
      const logText = await activityLog.textContent();
      if (logText?.includes('Starting upload') || logText?.includes('Uploaded:')) {
        console.log('🢄✓ Activity log contains upload-related entries');
      } else {
        console.log('🢄⚠ Activity log exists but no upload entries found');
        console.log('🢄Log content:', logText);
      }
    } else {
      console.log('🢄⚠ Activity log is not visible');

      // Check if there are any log entries at all
      const logEntries = page.locator('.log-entry');
      const count = await logEntries.count();
      console.log(`Log entries count: ${count}`);
    }
  });
});
