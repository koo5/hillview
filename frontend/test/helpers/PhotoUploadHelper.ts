import { browser, $, $$ } from '@wdio/globals';

/**
 * Helper for photo upload verification and source management
 * Consolidates complex logic from comprehensive-photo-capture.test.ts
 */
export class PhotoUploadHelper {
    private capturedPhotoTimestamp?: number;
    private capturedPhotoName?: string;

    /**
     * Generate unique photo identifier for tracking
     */
    generatePhotoIdentifier(): { timestamp: number; name: string } {
        const timestamp = Date.now();
        const randomSuffix = Math.random().toString(36).substring(2, 10);
        const name = `test_photo_${timestamp}_${randomSuffix}`;
        
        // Store for later verification
        this.capturedPhotoTimestamp = timestamp;
        this.capturedPhotoName = name;
        
        return { timestamp, name };
    }

    /**
     * Get the current photo identifier
     */
    getCurrentPhotoIdentifier(): { timestamp?: number; name?: string } {
        return {
            timestamp: this.capturedPhotoTimestamp,
            name: this.capturedPhotoName
        };
    }

    /**
     * Wait for an element with multiple selector attempts
     */
    async waitForElementWithRetries(selectors: string[], timeout: number = 10000): Promise<WebdriverIO.Element | null> {
        for (const selector of selectors) {
            try {
                const element = await $(selector);
                await element.waitForExist({ timeout: timeout / selectors.length });
                if (await element.isDisplayed()) {
                    return element;
                }
            } catch (error) {
                console.log(`Selector "${selector}" not found, trying next...`);
            }
        }
        return null;
    }

    /**
     * Navigate to gallery mode
     */
    async navigateToGallery(): Promise<void> {
        console.log('📷 Navigating to gallery mode...');
        
        // Try to go back to main screen first
        await browser.back();
        await browser.pause(1000);
        
        // Look for gallery button or photos view
        const gallerySelectors = [
            '//android.widget.Button[@text="Gallery"]',
            '//android.widget.Button[contains(@text, "Photos")]',
            '//android.widget.Button[contains(@text, "View")]',
            '//*[contains(@text, "Gallery")]'
        ];
        
        const galleryButton = await this.waitForElementWithRetries(gallerySelectors);
        if (galleryButton) {
            await galleryButton.click();
            await browser.pause(2000);
            console.log('📷 Navigated to gallery mode');
        } else {
            console.log('📷 Gallery button not found, assuming already in gallery mode');
        }
    }

    /**
     * Toggle HillViewSource with specified intervals
     */
    async toggleHillViewSourceWithInterval(intervalSeconds: number = 20, maxAttempts: number = 10): Promise<boolean> {
        console.log(`🔄 Starting HillViewSource toggle with ${intervalSeconds}s intervals (max ${maxAttempts} attempts)...`);
        
        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            console.log(`🔄 Toggle attempt ${attempt}/${maxAttempts}`);
            
            try {
                // Look for HillViewSource toggle
                const sourceSelectors = [
                    '//android.widget.CheckBox[contains(@text, "HillView")]',
                    '//android.widget.Switch[contains(@text, "HillView")]',
                    '//android.widget.ToggleButton[contains(@text, "HillView")]',
                    '//*[contains(@text, "HillView") and (@class="android.widget.CheckBox" or @class="android.widget.Switch" or @class="android.widget.ToggleButton")]'
                ];
                
                const sourceToggle = await this.waitForElementWithRetries(sourceSelectors, 5000);
                if (sourceToggle) {
                    await sourceToggle.click();
                    await browser.pause(1000);
                    console.log(`🔄 HillViewSource toggled (attempt ${attempt})`);
                    
                    // Check if our photo appeared after toggling
                    if (await this.checkForCapturedPhoto()) {
                        console.log('📷 Captured photo found after toggle!');
                        return true;
                    }
                } else {
                    console.log('🔄 HillViewSource toggle not found in this view');
                }
                
                // Wait for the specified interval before next attempt
                if (attempt < maxAttempts) {
                    console.log(`⏳ Waiting ${intervalSeconds} seconds before next toggle...`);
                    await browser.pause(intervalSeconds * 1000);
                }
                
            } catch (error) {
                console.log(`❌ Error during toggle attempt ${attempt}:`, error);
            }
        }
        
        console.log('❌ Max toggle attempts reached without finding photo');
        return false;
    }

    /**
     * Check for captured photo using original filename data attribute
     */
    async checkForCapturedPhoto(): Promise<boolean> {
        if (!this.capturedPhotoName || !this.capturedPhotoTimestamp) {
            console.log('❌ No photo identifier available for checking');
            return false;
        }

        console.log(`🔍 Looking for captured photo with identifier: ${this.capturedPhotoName}`);
        
        try {
            // Look for photo elements with data-testid attributes containing our photo identifier
            const photoSelectors = [
                `//android.widget.Image[@data-testid="${this.capturedPhotoName}"]`,
                `//android.widget.Image[contains(@data-testid, "${this.capturedPhotoTimestamp}")]`,
                `//*[@data-testid="${this.capturedPhotoName}"]`,
                `//*[contains(@data-testid, "${this.capturedPhotoTimestamp}")]`,
                // Also check for elements with original filename attributes
                `//android.widget.Image[@data-original-filename="${this.capturedPhotoName}"]`,
                `//*[@data-original-filename="${this.capturedPhotoName}"]`,
                // Check for recently uploaded photos (fallback)
                '//android.widget.Image[contains(@content-desc, "test_photo")]',
                '//android.widget.Button[contains(@text, "Thumbnail") and contains(@content-desc, "test_photo")]'
            ];
            
            for (const selector of photoSelectors) {
                try {
                    const photoElement = await $(selector);
                    if (await photoElement.isExisting() && await photoElement.isDisplayed()) {
                        console.log(`📷 Found captured photo using selector: ${selector}`);
                        return true;
                    }
                } catch (error) {
                    // Continue to next selector
                }
            }
            
            // Fallback: look for any recently added photos
            const allPhotos = await $$('//android.widget.Image');
            const allThumbnails = await $$('//android.widget.Button[@text="Thumbnail"]');
            
            const totalPhotoElements = allPhotos.length + allThumbnails.length;
            console.log(`📷 Found ${totalPhotoElements} total photo elements in gallery`);
            
            if (totalPhotoElements > 0) {
                // Check if any photos have recent timestamps
                const recentThreshold = this.capturedPhotoTimestamp - 30000; // 30 seconds before capture
                
                for (const photo of [...allPhotos, ...allThumbnails]) {
                    try {
                        const contentDesc = await photo.getAttribute('content-desc');
                        const dataTestId = await photo.getAttribute('data-testid');
                        const originalFilename = await photo.getAttribute('data-original-filename');
                        
                        // Check if any attributes contain our photo identifier
                        if (contentDesc?.includes(this.capturedPhotoName) || 
                            dataTestId?.includes(this.capturedPhotoName) || 
                            originalFilename?.includes(this.capturedPhotoName) ||
                            contentDesc?.includes(this.capturedPhotoTimestamp.toString()) ||
                            dataTestId?.includes(this.capturedPhotoTimestamp.toString())) {
                            console.log('📷 Found captured photo by attribute matching');
                            return true;
                        }
                    } catch (error) {
                        // Continue checking other photos
                    }
                }
            }
            
            return false;
        } catch (error) {
            console.log('❌ Error while checking for captured photo:', error);
            return false;
        }
    }

    /**
     * Navigate to photos settings where auto-upload is configured
     */
    async navigateToPhotosSettings(): Promise<void> {
        console.log('⚙️ Navigating to photos settings...');
        
        // Try to find and click menu button
        const menuSelectors = [
            '//android.widget.Button[@text="Toggle menu"]',
            '//android.widget.Button[contains(@text, "Menu")]',
            '//android.widget.Button[contains(@text, "☰")]'
        ];
        
        const menuButton = await this.waitForElementWithRetries(menuSelectors);
        if (menuButton) {
            await menuButton.click();
            await browser.pause(1000);
            
            // Look for photos/upload link
            const photosSelectors = [
                '//android.widget.TextView[@text="Photos"]',
                '//*[contains(@text, "Photos")]',
                '//android.widget.Button[contains(@text, "Photos")]',
                '//*[contains(@text, "Upload")]'
            ];
            
            const photosLink = await this.waitForElementWithRetries(photosSelectors);
            if (photosLink) {
                await photosLink.click();
                await browser.pause(2000);
                
                // Now look for the settings button on the photos page
                const settingsButtonSelectors = [
                    '//android.widget.Button[contains(@text, "Settings")]',
                    '//*[contains(@text, "Settings")][@class="android.widget.Button"]'
                ];
                
                const settingsButton = await this.waitForElementWithRetries(settingsButtonSelectors);
                if (settingsButton) {
                    await settingsButton.click();
                    await browser.pause(1000);
                    console.log('⚙️ Navigated to photos settings');
                    return;
                }
            }
        }
        
        // Fallback: try alternative navigation
        console.log('❌ Could not find photos settings, trying alternative navigation...');
        throw new Error('Could not navigate to photos settings');
    }

    /**
     * Enable automatic upload in photos settings
     */
    async enableAutomaticUpload(): Promise<void> {
        console.log('☁️ Enabling automatic upload...');
        
        // Look for auto-upload checkbox (now simplified without folder path)
        const uploadSelectors = [
            '//*[@data-testid="auto-upload-checkbox"]',
            '//android.widget.CheckBox[contains(@text, "Enable auto-upload")]',
            '//android.widget.CheckBox[contains(@text, "automatic") or contains(@text, "auto")]',
            '//*[contains(@text, "Enable auto-upload")][@class="android.widget.CheckBox"]'
        ];
        
        const uploadToggle = await this.waitForElementWithRetries(uploadSelectors);
        if (uploadToggle) {
            const isChecked = await uploadToggle.getAttribute('checked');
            if (isChecked !== 'true') {
                await uploadToggle.click();
                await browser.pause(500);
                
                // Save the settings
                const saveButtonSelectors = [
                    '//*[@data-testid="save-settings-button"]',
                    '//android.widget.Button[contains(@text, "Save")]',
                    '//android.widget.Button[contains(@text, "Save Settings")]'
                ];
                
                const saveButton = await this.waitForElementWithRetries(saveButtonSelectors);
                if (saveButton) {
                    await saveButton.click();
                    await browser.pause(1000);
                    console.log('☁️ Automatic upload enabled and settings saved');
                } else {
                    console.log('☁️ Automatic upload enabled but could not find save button');
                }
            } else {
                console.log('☁️ Automatic upload was already enabled');
            }
        } else {
            console.log('❌ Auto-upload toggle not found, continuing...');
        }
    }

    /**
     * Complete workflow: setup auto-upload, navigate to gallery, and verify photo upload
     */
    async performCompleteUploadVerification(intervalSeconds: number = 20, maxAttempts: number = 10): Promise<boolean> {
        try {
            console.log('☁️ Starting complete upload verification workflow...');
            
            // Step 1: Navigate to photos settings and enable auto-upload
            try {
                await this.navigateToPhotosSettings();
                await this.enableAutomaticUpload();
                
                // Go back to main screen
                await browser.back();
                await browser.pause(1000);
            } catch (error) {
                console.log('⚠️ Could not configure auto-upload settings, continuing with verification...');
            }
            
            // Step 2: Navigate to gallery mode
            await this.navigateToGallery();
            
            // Step 3: Toggle HillViewSource and wait for photo to appear
            const photoFound = await this.toggleHillViewSourceWithInterval(intervalSeconds, maxAttempts);
            
            if (!photoFound) {
                // Final attempt to find the photo
                console.log('🔍 Making final attempt to find captured photo...');
                const finalCheck = await this.checkForCapturedPhoto();
                return finalCheck;
            }
            
            console.log('🎉 Upload verification workflow completed successfully!');
            return true;
            
        } catch (error) {
            console.error('❌ Upload verification workflow failed:', error);
            return false;
        }
    }
}