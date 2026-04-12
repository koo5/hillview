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

const HERO_PANORAMA_PATH =
    '/?lat=50.11691142317276&lon=14.488375782966616&zoom=20&bearing=139.06&photo=hillview-333e8851-c59b-4133-bce5-2d1ddc2ce335';

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
    await browser.pause(3000);
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
        await navigateTo(HERO_PANORAMA_PATH);
        await browser.pause(4000);
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
        await browser.pause(2000);
        await shot('best-of');
    });

    it('activity feed', async () => {
        await navigateTo('/activity');
        await browser.pause(2000);
        await shot('activity-feed');
    });

    it('settings', async () => {
        await navigateTo('/settings');
        await browser.pause(1500);
        await shot('settings');
    });

    it('camera capture', async () => {
        await navigateTo('/');
        await browser.pause(2000);
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
        await navigateTo('/login');
        await browser.pause(1500);
        await shot('login-page');
    });

    it('about page', async () => {
        await navigateTo('/about');
        await browser.pause(1500);
        await shot('about-page');
    });
});
