import { acquireTestLock } from './testLock';

/**
 * Global setup for screenshot runs.
 *
 * Only acquires the shared cross-suite lock — screenshots must not run
 * concurrently with regular tests (which recreate users / wipe DB state
 * and would cause the screenshot process to capture inconsistent UI),
 * but screenshots themselves should NOT wipe or recreate anything.
 * They capture whatever content already exists on the target backend.
 */
async function globalSetup() {
  console.log('Screenshots Global Setup: Acquiring test lock...');
  await acquireTestLock();
  console.log('Screenshots Global Setup: Lock acquired, starting capture');
}

export default globalSetup;
