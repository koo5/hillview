import { browser } from '@wdio/globals';

describe('Android Simple Health Check', () => {
    it('should launch app and detect WebView successfully', async () => {
        console.log('🏥 Starting simple app health check...');

        // Wait for app to fully load
        await browser.pause(3000);

        // Check that we can get the page source (indicates app is responsive)
        const pageSource = await browser.getPageSource();
        expect(pageSource.length).toBeGreaterThan(1000, 'Page source should contain substantial content');

        // Check for WebView presence in page source
        expect(pageSource).toContain('android.webkit.WebView', 'WebView should be present in the UI hierarchy');

        // Check for Hillview app-specific content
        expect(pageSource).toContain('cz.hillviedev', 'App package should be correct');

        // Optional: Check for map-related content (indicates the main UI loaded)
        const hasMapContent = pageSource.includes('Zoom') || pageSource.includes('Toggle') || pageSource.includes('Leaflet');
        if (hasMapContent) {
            console.log('✅ Map interface detected - app fully loaded');
        } else {
            console.log('ℹ️ Map not yet loaded, but app is responsive');
        }

        console.log('✅ Simple health check passed - app is functional');
    });

    it('should be able to get device information', async () => {
        console.log('📱 Testing device capabilities...');

        // Test that we can get basic device info (indicates Appium is working properly)
        const deviceInfo = await browser.execute('mobile: deviceInfo');
        expect(deviceInfo).toBeDefined();
        expect(deviceInfo.platformVersion).toBe('16', 'Platform version should match emulator');

        // Test that we can get orientation
        const orientation = await browser.getOrientation();
        expect(['PORTRAIT', 'LANDSCAPE']).toContain(orientation, 'Orientation should be valid');

        console.log('✅ Device capabilities test passed');
    });

    it('should be able to click the menu button', async () => {
        console.log('🖱️ Testing menu button interaction...');

        // Wait for app to fully load
        await browser.pause(3000);

        console.log('🔍 Verifying menu button exists in page source...');

        // Verify the button exists in the page source
        const pageSourceBefore = await browser.getPageSource();
        expect(pageSourceBefore).toContain('Toggle menu', 'Menu button should exist in page source');

        // Log how the "Toggle menu" text appears in the page source for debugging
        const lines = pageSourceBefore.split('\n');
        for (const line of lines) {
            if (line.includes('Toggle menu')) {
                console.log('📋 Found Toggle menu in:', line.substring(0, 300));
            }
        }

        console.log('🔍 Finding and clicking menu button...');

        // In WebView apps, text may appear in content-desc rather than text attribute
        // Try content-desc first, then text
        let menuBtn = await $('//*[@content-desc="Toggle menu"]');
        if (!await menuBtn.isExisting()) {
            console.log('ℹ️ Not found via content-desc, trying text attribute...');
            menuBtn = await $('//*[@text="Toggle menu"]');
        }
        if (!await menuBtn.isExisting()) {
            console.log('ℹ️ Not found via text, trying accessibility id...');
            menuBtn = await $('~Toggle menu');
        }
        await menuBtn.click();

        console.log('✅ Menu button clicked successfully');

        // Wait a moment for any UI changes to occur
        await browser.pause(2000);

        // Get page source after click to verify the app is still responsive
        const pageSourceAfter = await browser.getPageSource();
        expect(pageSourceAfter.length).toBeGreaterThan(1000);

        console.log('📄 Checking if click had any effect...');

        // Check if the click changed anything (optional verification)
        if (pageSourceAfter !== pageSourceBefore) {
            console.log('✅ Page content changed after click - menu interaction detected');
        } else {
            console.log('ℹ️ Page content unchanged - click registered but no visible UI change');
        }

        console.log('✅ Menu button interaction test passed');
    });
});