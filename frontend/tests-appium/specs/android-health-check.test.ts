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
        
        // Check for expected elements
        const takePhotoButton = await $('//android.widget.Button[@text="Take photo"]');
        const buttonExists = await takePhotoButton.isExisting();
        expect(buttonExists).toBe(true, 'Take photo button should be visible');
        
        // Check WebView is responsive
        const webView = await $('android.webkit.WebView');
        expect(await webView.isDisplayed()).toBe(true, 'WebView should be displayed');
        
        console.log('✅ App health check passed - no errors detected');
    });
    
    it('should be able to find and display UI elements', async () => {
        console.log('🖱️ Testing UI elements visibility...');
        
        const takePhotoButton = await $('//android.widget.Button[@text="Take photo"]');
        await takePhotoButton.waitForDisplayed({ timeout: 5000 });
        
        // Verify button is displayed (avoid isClickable which has issues)
        expect(await takePhotoButton.isDisplayed()).toBe(true, 'Take photo button should be displayed');
        
        // Check if button exists
        expect(await takePhotoButton.isExisting()).toBe(true, 'Take photo button should exist');
        
        console.log('✅ UI elements visibility test passed');
    });
});