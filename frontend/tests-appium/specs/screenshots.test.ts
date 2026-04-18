import { browser } from '@wdio/globals';
import {
    acceptPermissionDialogIfPresent,
    byTestId,
    ensureWebViewContext,
    TESTID,
} from '../helpers/selectors';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Android screenshots for Play Store listing and documentation.
 *
 * Auto-detects device type from screen resolution and saves to:
 *   docs/screenshots/android-phone/
 *   docs/screenshots/android-tablet-7/
 *   docs/screenshots/android-tablet-10/
 */

let outDir: string;

function classifyDevice(widthPx: number, heightPx: number, density: number): string {
    const shortSideDp = Math.min(widthPx, heightPx) / density;
    if (shortSideDp >= 800) return 'android-tablet-10';
    if (shortSideDp >= 560) return 'android-tablet-7';
    return 'android-phone';
}

async function shot(name: string) {
    const filePath = path.join(outDir, `${name}.png`);
    await browser.saveScreenshot(filePath);
    console.log(`  📸 ${filePath}`);
}

async function navigateTo(urlPath: string) {
    await ensureWebViewContext();
    await browser.execute((p: string) => { window.location.href = p; }, urlPath);
    // Brief pause for SPA route transition to start.
    await browser.pause(500);
}

/** Wait for a data-testid element to be visible (DOM check via JS, avoids WD element staleness). */
async function waitForTestId(testId: string, timeout = 15_000) {
    await ensureWebViewContext();
    await browser.waitUntil(async () => {
        return browser.execute((tid: string) => {
            const el = document.querySelector<HTMLElement>(`[data-testid="${tid}"]`);
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
        }, testId);
    }, { timeout, timeoutMsg: `[data-testid="${testId}"] not visible after ${timeout}ms` });
}

/**
 * Wait for content, with a single reload if the first attempt stalls.
 * The dev backend occasionally hangs on the first request after startup.
 */
async function waitForTestIdWithReload(testId: string, urlPath: string, timeout = 30_000) {
    try {
        await waitForTestId(testId, timeout);
    } catch (e) {
        console.log(`  ⚠️  ${testId} not visible after ${timeout}ms — reloading ${urlPath}`);
        await navigateTo(urlPath);
        await waitForTestId(testId, timeout);
    }
}

/** Wait until images inside a container have loaded (at least one). */
async function waitForImages(containerTestId: string, timeout = 15_000) {
    await ensureWebViewContext();
    await browser.waitUntil(async () => {
        return browser.execute((tid: string) => {
            const container = document.querySelector(`[data-testid="${tid}"]`);
            if (!container) return false;
            const imgs = container.querySelectorAll('img');
            if (imgs.length === 0) return false;
            return Array.from(imgs).some(img => img.complete && img.naturalWidth > 0);
        }, containerTestId);
    }, { timeout, timeoutMsg: `No loaded images in [data-testid="${containerTestId}"] after ${timeout}ms` });
}

describe('Android Screenshots', () => {

    before(async () => {
        const { width, height } = await driver.getWindowSize();
        const caps = await driver.getSession() as any;
        const density = caps.deviceScreenDensity
            ? caps.deviceScreenDensity / 160
            : 2.75;
        const deviceCategory = classifyDevice(width, height, density);
        outDir = path.resolve(__dirname, `../../../docs/screenshots/${deviceCategory}`);
        fs.mkdirSync(outDir, { recursive: true });
        console.log(`\n📱 Device: ${deviceCategory} (${width}×${height})`);
        console.log(`📂 Output: ${outDir}\n`);

        await browser.pause(5000);
        await acceptPermissionDialogIfPresent(3000);
    });

    it('hero panorama', async () => {
        // Pick the current top-ranked photo as hero — avoids hard-coding a photo ID.
        await navigateTo('/bestof');
        await waitForTestId('bestof-photo-grid', 30_000);
        await waitForImages('bestof-photo-grid', 30_000);
        // Click the first photo card — its PhotoItem <a> links to the map view.
        await ensureWebViewContext();
        const firstCard = await $('[data-testid="bestof-photo-card"]');
        await firstCard.$('a').click();
        // Wait for the map + active photo slot to render.
        await $('[data-testid="main-photo"].front').waitForDisplayed({ timeout: 20_000 });
        await browser.waitUntil(async () => {
            return browser.execute(() => {
                const img = document.querySelector<HTMLImageElement>('[data-testid="main-photo"].front');
                return img !== null && img.complete && img.naturalWidth > 0;
            });
        }, { timeout: 20_000, timeoutMsg: 'Hero photo image did not load' });
        // Let map tiles and annotation overlay finish rendering.
        await browser.pause(2000);
        await shot('hero-panorama');
    });

    it('navigation menu', async () => {
        const btn = await byTestId(TESTID.hamburgerMenu);
        await btn.waitForDisplayed({ timeout: 10_000 });
        await btn.click();
        await browser.pause(800);
        await shot('navigation-menu');
        await btn.click();
        await browser.pause(500);
    });

    it('best of', async () => {
        await navigateTo('/bestof');
        await waitForTestId('bestof-photo-grid', 30_000);
        await waitForImages('bestof-photo-grid', 30_000);
        // Let thumbnails finish rendering.
        await browser.pause(1000);
        await shot('best-of');
    });

    it('activity feed', async () => {
        await navigateTo('/activity');
        await waitForTestId('activity-list', 30_000);
        await waitForImages('activity-list', 30_000);
        await browser.pause(1000);
        await shot('activity-feed');
    });

    it('settings', async () => {
        await navigateTo('/settings');
        await waitForTestId('advanced-menu-link');
        await browser.pause(500);
        await shot('settings');
    });

    it('external camera settings', async () => {
        await navigateTo('/settings/advanced');
        await waitForTestId('qr-timestamp-link');
        // Scroll the QR timestamp link into view so the External Camera section is visible.
        await browser.execute(() => {
            document.querySelector('[data-testid="qr-timestamp-link"]')?.scrollIntoView({ block: 'center' });
        });
        await browser.pause(500);
        await shot('external-camera-settings');
    });

    it('camera capture', async () => {
        await navigateTo('/');
        await waitForTestId(TESTID.cameraButton);
        const cameraBtn = await byTestId(TESTID.cameraButton);
        await cameraBtn.click();
        await browser.pause(1000);
        await acceptPermissionDialogIfPresent(3000);
        try {
            const allowBtn = await byTestId('allow-camera-btn');
            if (await allowBtn.isExisting()) {
                await allowBtn.click();
                await browser.pause(1000);
                await acceptPermissionDialogIfPresent(3000);
            }
        } catch { /* already allowed */ }
        await browser.pause(2000);
        await shot('camera-capture');
        const cameraBtnAgain = await byTestId(TESTID.cameraButton);
        await cameraBtnAgain.click();
        await browser.pause(500);
    });

    it('login page', async () => {
        // Log out first — otherwise /login redirects an authenticated user away.
        await navigateTo('/');
        await waitForTestId(TESTID.hamburgerMenu);
        const hamburger = await byTestId(TESTID.hamburgerMenu);
        await hamburger.click();
        await browser.pause(500);
        const logoutBtn = await $('[data-testid="nav-logout-button"]');
        if (await logoutBtn.isExisting() && await logoutBtn.isDisplayed()) {
            await logoutBtn.click();
            await browser.pause(1000);
        }
        await navigateTo('/login');
        await waitForTestId('login-form');
        // Clear any autofilled values so the form looks fresh in the screenshot.
        await browser.execute(() => {
            document.querySelectorAll<HTMLInputElement>('[data-testid="login-form"] input').forEach(input => {
                input.value = '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
        await browser.pause(500);
        await shot('login-page');
    });

    it('about page', async () => {
        await navigateTo('/about');
        // Static content — wait for a section to render.
        await ensureWebViewContext();
        await $('section.about-section').waitForDisplayed({ timeout: 10_000 });
        await browser.pause(500);
        await shot('about-page');
    });
});
