import { test, expect } from './fixtures';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';

test.describe('Settings Visibility', () => {
  let testPasswords: { test: string; admin: string; testuser: string };

  test.beforeEach(async () => {
    // Clean up and recreate test users before each test
    const result = await createTestUsers();
    testPasswords = result.passwords;
  });

});
