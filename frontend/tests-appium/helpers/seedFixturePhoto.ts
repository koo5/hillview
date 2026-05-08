/**
 * Fixture photo seeding for Appium screenshot runs.
 *
 * Mirrors `tests-playwright/helpers/globalSetupScreenshots.ts`: drives the
 * web `/photos` upload flow in a headless Chromium so the seeded photo
 * goes through the real ECDSA-signed `secureUpload` path and the worker
 * pipeline. End state matches what Playwright produces — same fixture
 * file, same Photo row, same generated sizes.
 *
 * Reuses the existing Playwright helpers (`loginAsTestUser`, `uploadPhoto`)
 * via sibling-package imports so the flow stays in lockstep with what
 * Playwright already validates.
 *
 * The Appium runner can't reuse the Playwright web dev server (it isn't
 * running by the time Appium starts), so we spawn our own `bun run dev`
 * on a dedicated port. The spawned SPA defaults to localhost:8055/api
 * because `TAURI_MOBILE` is false in a regular browser context.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import { chromium, type Browser } from '@playwright/test';

import { loginAsTestUser } from '../../tests-playwright/helpers/testUsers';
import { uploadPhoto } from '../../tests-playwright/helpers/photoUpload';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.resolve(__dirname, '../..');
const FIXTURE_FILENAME = 'prosecke-skaly-fixture.jpg';

/** Same path the Playwright suite writes — interchangeable consumers. */
export const SCREENSHOT_FIXTURE_INFO_PATH = path.join(os.tmpdir(), 'hillview-screenshot-fixture.json');

/** 8212 is in the backend CORS allowlist (`common/config.py`); Playwright uses
 * the same port and has released it by the time Appium runs. Override via
 * SEED_DEV_PORT, but any new port must also be added to the CORS list. */
const SEED_DEV_PORT = parseInt(process.env.SEED_DEV_PORT || '8212', 10);
const SEED_BASE_URL = `http://localhost:${SEED_DEV_PORT}`;

let _seededPhotoId: string | null = null;

export async function seedFixturePhoto(testUserPassword: string): Promise<string> {
    if (_seededPhotoId) return _seededPhotoId;

    console.log(`[seed] starting dev server at ${SEED_BASE_URL}`);
    const dev = await startDevServer();
    let browser: Browser | null = null;
    try {
        browser = await chromium.launch({ headless: true });
        const context = await browser.newContext({ baseURL: SEED_BASE_URL });
        const page = await context.newPage();
        page.on('console', (msg) => {
            const t = msg.type();
            if (t === 'error' || t === 'warning') console.log(`[seed:browser ${t}]`, msg.text());
        });
        await loginAsTestUser(page, testUserPassword);
        const photoId = await uploadPhoto(page, FIXTURE_FILENAME);
        if (!photoId) throw new Error('Upload returned empty photo id');
        _seededPhotoId = photoId;
        fs.writeFileSync(SCREENSHOT_FIXTURE_INFO_PATH, JSON.stringify({ photoId }));
        console.log(`[seed] uploaded fixture photo ${photoId} → ${SCREENSHOT_FIXTURE_INFO_PATH}`);
        return photoId;
    } finally {
        if (browser) await browser.close().catch(() => {});
        await stopDevServer(dev);
    }
}

async function startDevServer(): Promise<ChildProcess> {
    // Strip backend overrides so the SPA picks the localhost:8055/api default.
    const env: NodeJS.ProcessEnv = { ...process.env, VITE_DEV_PORT: String(SEED_DEV_PORT) };
    delete env.VITE_BACKEND;
    delete env.VITE_BACKEND_ANDROID;

    const proc = spawn('bun', ['run', 'dev'], {
        cwd: FRONTEND_DIR,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
    });
    proc.stdout?.on('data', (chunk) => process.stdout.write(`[seed-dev] ${chunk}`));
    proc.stderr?.on('data', (chunk) => process.stderr.write(`[seed-dev] ${chunk}`));
    proc.on('exit', (code, signal) => {
        if (code !== 0 && code !== null) {
            console.warn(`[seed-dev] exited code=${code} signal=${signal}`);
        }
    });

    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
        try {
            const res = await fetch(SEED_BASE_URL, { signal: AbortSignal.timeout(2000) });
            if (res.status < 500) return proc;
        } catch { /* not yet */ }
        await new Promise((r) => setTimeout(r, 500));
    }
    proc.kill('SIGTERM');
    throw new Error(`Seed dev server failed to come up at ${SEED_BASE_URL} within 60s`);
}

async function stopDevServer(proc: ChildProcess): Promise<void> {
    if (proc.killed || proc.exitCode !== null) return;
    proc.kill('SIGTERM');
    await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
            try { proc.kill('SIGKILL'); } catch { /* already gone */ }
            resolve();
        }, 3000);
        proc.once('exit', () => { clearTimeout(timeout); resolve(); });
    });
}
