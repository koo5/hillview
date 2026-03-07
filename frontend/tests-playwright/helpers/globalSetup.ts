import { acquireTestLock } from './testLock';
import { setupCleanTestEnvironment } from './testUsers';

/**
 * Global setup that runs once before all tests
 * Acquires cross-suite lock, then clears database
 */
async function globalSetup() {
  console.log('Global Setup: Acquiring test lock...');
  await acquireTestLock();

  console.log('Global Setup: Clearing database...');
  try {
    await setupCleanTestEnvironment();
    console.log('Global Setup: Database cleared, ready for tests');
  } catch (error) {
    console.error('Global Setup failed:', error);
    throw error;
  }
}

export default globalSetup;