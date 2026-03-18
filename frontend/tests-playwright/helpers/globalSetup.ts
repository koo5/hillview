import { acquireTestLock } from './testLock';
import { setupCleanTestEnvironment, recreateTestUsers } from './testUsers';

/**
 * Global setup that runs once before all tests
 * Acquires cross-suite lock, clears database, and creates test users
 */
async function globalSetup() {
  console.log('Global Setup: Acquiring test lock...');
  await acquireTestLock();

  console.log('Global Setup: Clearing database...');
  try {
    await setupCleanTestEnvironment();
    console.log('Global Setup: Database cleared');
  } catch (error) {
    console.error('Global Setup failed:', error);
    throw error;
  }

  console.log('Global Setup: Creating test users...');
  try {
    await recreateTestUsers();
    console.log('Global Setup: Test users created, ready for tests');
  } catch (error) {
    console.error('Global Setup: Failed to create test users:', error);
    throw error;
  }
}

export default globalSetup;
