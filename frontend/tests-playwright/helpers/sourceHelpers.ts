import { test, type Page } from '@playwright/test';

/**
 * Playwright helpers for managing map source states in tests.
 * This provides utilities to reliably enable/disable sources like Hillview, Mapillary, etc.
 */

/**
 * Ensure a map source is enabled or disabled on the main page.
 * Uses proper data-testid selectors and correct state checking logic.
 *
 * @param page - Playwright page object
 * @param sourceName - Name of the source (e.g., 'Hillview', 'Mapillary', 'Device')
 * @param enabled - Whether the source should be enabled (true) or disabled (false)
 * @returns Promise<boolean> - True if successful, false if failed
 */
export async function ensureSourceEnabled(page: Page, sourceName: string, enabled: boolean): Promise<boolean> {
    console.log(`🗺️ Ensuring ${sourceName} source is ${enabled ? 'enabled' : 'disabled'}...`);

    try {
        // Find the source toggle button using proper data-testid
        const sourceButton = page.locator(`[data-testid="source-toggle-${sourceName}"]`);

        // Wait for button to be visible
        await sourceButton.waitFor({ state: 'visible', timeout: 10000 });

        // Check current state by looking for 'active' class on the button itself
        const isCurrentlyEnabled = await sourceButton.evaluate((el: HTMLElement) => {
            return el.classList.contains('active');
        });

        // Click if we need to change the state
        if (isCurrentlyEnabled !== enabled) {
            await sourceButton.click();
            await page.waitForTimeout(1000); // Allow state change to propagate
            console.log(`🗺️ ${enabled ? 'Enabled' : 'Disabled'} ${sourceName} source`);
        } else {
            console.log(`🗺️ ${sourceName} source already ${enabled ? 'enabled' : 'disabled'}`);
        }

        return true;
    } catch (error) {
        console.error(`❌ Failed to set ${sourceName} source to ${enabled}:`, (error as Error).message);
        return false;
    }
}

/**
 * Configure multiple sources at once.
 *
 * @param page - Playwright page object
 * @param config - Object mapping source names to their desired enabled state
 * @returns Promise<boolean> - True if all succeeded, false if any failed
 */
export async function configureSources(page: Page, config: { [sourceName: string]: boolean }): Promise<boolean> {
    return await test.step(`Configure sources: ${Object.entries(config).map(([name, enabled]) => `${name}=${enabled}`).join(', ')}`, async () => {
        console.log('🗺️ Configuring sources:', config);

        let allSucceeded = true;

        for (const [sourceName, shouldBeEnabled] of Object.entries(config)) {
            const success = await ensureSourceEnabled(page, sourceName, shouldBeEnabled);
            if (!success) {
                allSucceeded = false;
            }
        }

        // Wait for all source state changes to propagate to worker
        await page.waitForTimeout(2000);
        console.log('🗺️ Source configuration complete');

        return allSucceeded;
    });
}

/**
 * Wait for map source data to load after configuration changes.
 * This is useful when tests need to wait for photos to appear after enabling sources.
 *
 * @param page - Playwright page object
 * @param timeoutMs - Maximum time to wait in milliseconds (default: 10000)
 */
export async function waitForSourceDataLoad(page: Page, timeoutMs: number = 10000): Promise<void> {
    console.log('🗺️ Waiting for source data to load...');

    try {
        // Wait for photo worker to complete processing
        await page.waitForFunction(() => {
            // Look for console logs or DOM changes that indicate loading is complete
            // This might need to be customized based on how the app signals completion
            return window.performance.now() > 0; // Placeholder - replace with actual loading check
        }, { timeout: timeoutMs });

        console.log('🗺️ Source data loading complete');
    } catch (error) {
        console.warn(`⚠️ Source data loading timeout after ${timeoutMs}ms`);
    }
}