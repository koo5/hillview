import { browser, $ } from '@wdio/globals';

describe('Android App Health Check', () => {
    it('should have working app with no errors visible', async () => {
        console.log('🏥 Starting comprehensive app health check...');
        
        // The app should already be launched by beforeTest hook
        // Now let's verify it's actually working
        
        // Check for error messages
        const errorPatterns = [
            'error sending request',
            'connection failed',
            'network error',
            'tauri error'
        ];
        
        for (const pattern of errorPatterns) {
            const errorEl = await $(`//*[contains(@text, "${pattern}")]`);
            const hasError = await errorEl.isExisting();
            expect(hasError).toBe(false, `Found error message: "${pattern}"`);
        }
        
        // Check for expected UI elements that should be visible on main screen
        const toggleMenuButton = await $('//android.widget.Button[@text="Toggle menu"]');
        const menuButtonExists = await toggleMenuButton.isExisting();
        expect(menuButtonExists).toBe(true, 'Toggle menu button should be visible');

        // Check for map controls (indicating app is fully loaded)
        const zoomInButton = await $('//android.widget.Button[@text="Zoom in"]');
        const zoomButtonExists = await zoomInButton.isExisting();
        expect(zoomButtonExists).toBe(true, 'Zoom controls should be visible (map loaded)');
        
        // Check WebView is responsive
        const webViews = await $$('android.webkit.WebView');
        expect(webViews.length).toBeGreaterThan(0, 'At least one WebView should exist');

        // Check the main WebView is displayed
        const mainWebView = webViews[1] || webViews[0]; // Try the second one first (main content), fallback to first
        expect(await mainWebView.isDisplayed()).toBe(true, 'Main WebView should be displayed');
        
        console.log('✅ App health check passed - no errors detected');
    });
    
    it('should be able to find and display UI elements', async () => {
        console.log('🖱️ Testing UI elements visibility...');

        // Test multiple UI elements that should be visible
        const toggleMenuButton = await $('//android.widget.Button[@text="Toggle menu"]');
        await toggleMenuButton.waitForDisplayed({ timeout: 5000 });

        // Verify button is displayed
        expect(await toggleMenuButton.isDisplayed()).toBe(true, 'Toggle menu button should be displayed');
        expect(await toggleMenuButton.isExisting()).toBe(true, 'Toggle menu button should exist');

        // Test zoom controls
        const zoomInButton = await $('//android.widget.Button[@text="Zoom in"]');
        expect(await zoomInButton.isDisplayed()).toBe(true, 'Zoom in button should be displayed');

        console.log('✅ UI elements visibility test passed');
    });
});