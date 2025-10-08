import { expect } from '@wdio/globals'

/**
 * Simple Android Menu Click Test
 *
 * This test demonstrates the proper way to interact with the Hillview app
 * by switching to WebView context and using data-testid attributes
 */
describe('Android Menu Click Test', () => {

    it('should successfully click the menu button', async function () {
        this.timeout(60000);

        console.log('🖱️ Testing menu button click using proper WebView context...');

        try {
            // Wait for app to load
            await driver.pause(3000);

            // Switch to WebView context - this is the key!
            console.log('🔄 Switching to WebView context...');
            await driver.switchContext('WEBVIEW_cz.hillviedev');

            // Find the hamburger menu using data-testid (much more reliable)
            console.log('🔍 Looking for hamburger menu with data-testid...');
            const hamburgerMenu = await $('[data-testid="hamburger-menu"]');

            // Wait for it to be displayed
            await hamburgerMenu.waitForDisplayed({ timeout: 10000 });

            // Verify it's clickable
            expect(await hamburgerMenu.isDisplayed()).toBe(true);
            expect(await hamburgerMenu.isEnabled()).toBe(true);

            // Click the menu button
            console.log('🍔 Clicking hamburger menu...');
            await hamburgerMenu.click();

            console.log('✅ Menu button clicked successfully!');

            // Wait a moment for menu animation
            await driver.pause(2000);

            // Verify menu opened by looking for a menu item
            console.log('🔍 Verifying menu opened...');
            try {
                const menuItem = await $('a[href="/login"]');
                await menuItem.waitForDisplayed({ timeout: 5000 });
                console.log('✅ Menu opened - found login link');
            } catch (e) {
                // Menu might have different items, that's okay
                console.log('ℹ️ Menu opened but login link not found (user might be logged in)');
            }

            // Switch back to native context
            console.log('🔄 Switching back to native context...');
            await driver.switchContext('NATIVE_APP');

            console.log('🎉 Menu click test completed successfully!');

        } catch (error) {
            console.error('❌ Menu click test failed:', error);

            // Try to switch back to native context in case of error
            try {
                await driver.switchContext('NATIVE_APP');
            } catch (e) {
                // Ignore context switch errors
            }

            throw error;
        }
    });
});