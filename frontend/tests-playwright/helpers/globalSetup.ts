import { setupCleanTestEnvironment } from './testUsers';

/**
 * Global setup that runs once before all tests
 * Only clears database - individual tests create users as needed
 */
async function globalSetup() {
  console.log('🧹 Global Setup: Clearing database...');

  try {
    await setupCleanTestEnvironment();
    console.log('✅ Global Setup: Database cleared, ready for tests');
  } catch (error) {
    console.error('❌ Global Setup failed:', error);
    throw error;
  }
}

export default globalSetup;