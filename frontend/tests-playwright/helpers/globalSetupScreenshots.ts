import { chromium } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { acquireTestLock } from './testLock';
import { recreateTestUsers, loginAsTestUser } from './testUsers';
import { uploadPhoto } from './photoUpload';

/**
 * Global setup for screenshot runs.
 *
 * By default: only acquires the shared cross-suite lock. Screenshots must
 * not run concurrently with regular tests (which recreate users / wipe DB
 * state) but the suite itself captures whatever content already exists on
 * the target backend — useful when pointing at production.
 *
 * With MOCK_SCREENSHOTS_DATA=1: ensures the test user exists (without wiping
 * the DB) and uploads a fixture panorama whose EXIF GPS sits at the canonical
 * Vyhlídka Prosecké skály coordinates. The seeded photo id is written to
 * SCREENSHOT_FIXTURE_INFO_PATH so the spec can build a hero URL pointing at
 * it instead of the production photo id. This makes the suite runnable on
 * a fresh dev environment without depending on prod data, while leaving any
 * existing local content in place.
 */

export const SCREENSHOT_FIXTURE_INFO_PATH = path.join(os.tmpdir(), 'hillview-screenshot-fixture.json');
const FIXTURE_FILENAME = 'prosecke-skaly-fixture.jpg';

async function seedFixturePhoto(baseURL: string, password: string): Promise<string> {
  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();
  try {
    await loginAsTestUser(page, password);
    const photoId = await uploadPhoto(page, FIXTURE_FILENAME);
    if (!photoId) throw new Error('Fixture upload returned empty photo id');
    return photoId;
  } finally {
    await context.close();
    await browser.close();
  }
}

async function globalSetup() {
  console.log('Screenshots Global Setup: Acquiring test lock...');
  await acquireTestLock();
  console.log('Screenshots Global Setup: Lock acquired');

  if (process.env.MOCK_SCREENSHOTS_DATA === '1') {
    console.log('Screenshots Global Setup: MOCK_SCREENSHOTS_DATA=1 — seeding fixture photo (DB not wiped)');
    const { passwords } = await recreateTestUsers();

    const baseURL = process.env.SCREENSHOT_URL || 'http://localhost:8212';
    const photoId = await seedFixturePhoto(baseURL, passwords.test);
    fs.writeFileSync(SCREENSHOT_FIXTURE_INFO_PATH, JSON.stringify({ photoId }));
    console.log(`Screenshots Global Setup: seeded fixture photo ${photoId} → ${SCREENSHOT_FIXTURE_INFO_PATH}`);
  } else {
    if (fs.existsSync(SCREENSHOT_FIXTURE_INFO_PATH)) fs.unlinkSync(SCREENSHOT_FIXTURE_INFO_PATH);
    console.log('Screenshots Global Setup: capturing existing backend content (no seed)');
  }
}

export default globalSetup;
