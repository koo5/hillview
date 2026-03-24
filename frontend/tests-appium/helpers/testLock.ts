/**
 * Re-export from the shared Playwright test lock.
 * Same lock file is used by Playwright, pytest, and Appium test suites.
 */
export { acquireTestLock, releaseTestLock } from '../../tests-playwright/helpers/testLock';
