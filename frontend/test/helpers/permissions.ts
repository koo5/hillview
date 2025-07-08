import { browser, $ } from '@wdio/globals';

export class PermissionHelper {
    private static readonly PERMISSION_DIALOG_TIMEOUT = 5000;
    
    // Android permission dialog selectors
    private static readonly SELECTORS = {
        // Android 11+ permission dialog
        permissionDialog: '//android.widget.LinearLayout[@resource-id="com.android.permissioncontroller:id/grant_dialog"]',
        allowButton: '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]',
        denyButton: '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_deny_button"]',
        allowOnceButton: '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]',
        allowAlwaysButton: '//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_always_button"]',
        
        // Alternative selectors for different Android versions
        alternativeAllow: '//android.widget.Button[contains(@text, "Allow") or contains(@text, "ALLOW")]',
        alternativeDeny: '//android.widget.Button[contains(@text, "Deny") or contains(@text, "DENY")]',
        alternativeWhileUsing: '//android.widget.Button[contains(@text, "While using") or contains(@text, "Only this time")]',
        
        // Permission message
        permissionMessage: '//android.widget.TextView[@resource-id="com.android.permissioncontroller:id/permission_message"]'
    };
    
    /**
     * Check if permission dialog is displayed
     */
    static async isPermissionDialogDisplayed(): Promise<boolean> {
        try {
            const dialog = await $(this.SELECTORS.permissionDialog);
            return await dialog.isDisplayed();
        } catch {
            // Try alternative check
            const allowButton = await $(this.SELECTORS.alternativeAllow);
            return await allowButton.isExisting();
        }
    }
    
    /**
     * Wait for permission dialog to appear
     */
    static async waitForPermissionDialog(timeout: number = this.PERMISSION_DIALOG_TIMEOUT): Promise<boolean> {
        try {
            const dialog = await $(this.SELECTORS.permissionDialog);
            await dialog.waitForExist({ timeout });
            return true;
        } catch {
            // Try alternative selector
            const allowButton = await $(this.SELECTORS.alternativeAllow);
            return await allowButton.waitForExist({ timeout });
        }
    }
    
    /**
     * Grant permission when dialog appears
     */
    static async grantPermission(allowAlways: boolean = false): Promise<void> {
        if (!await this.waitForPermissionDialog()) {
            throw new Error('Permission dialog did not appear');
        }
        
        // Try specific buttons first
        if (allowAlways) {
            const alwaysButton = await $(this.SELECTORS.allowAlwaysButton);
            if (await alwaysButton.isExisting()) {
                await alwaysButton.click();
                return;
            }
        }
        
        // Try "While using app" button
        const whileUsingButton = await $(this.SELECTORS.alternativeWhileUsing);
        if (await whileUsingButton.isExisting()) {
            await whileUsingButton.click();
            return;
        }
        
        // Try regular allow button
        const allowButton = await $(this.SELECTORS.allowButton);
        if (await allowButton.isExisting()) {
            await allowButton.click();
            return;
        }
        
        // Fallback to alternative allow button
        const altAllowButton = await $(this.SELECTORS.alternativeAllow);
        if (await altAllowButton.isExisting()) {
            await altAllowButton.click();
            return;
        }
        
        throw new Error('Could not find allow button on permission dialog');
    }
    
    /**
     * Deny permission when dialog appears
     */
    static async denyPermission(): Promise<void> {
        if (!await this.waitForPermissionDialog()) {
            throw new Error('Permission dialog did not appear');
        }
        
        // Try specific deny button first
        const denyButton = await $(this.SELECTORS.denyButton);
        if (await denyButton.isExisting()) {
            await denyButton.click();
            return;
        }
        
        // Fallback to alternative deny button
        const altDenyButton = await $(this.SELECTORS.alternativeDeny);
        if (await altDenyButton.isExisting()) {
            await altDenyButton.click();
            return;
        }
        
        throw new Error('Could not find deny button on permission dialog');
    }
    
    /**
     * Get permission dialog message text
     */
    static async getPermissionMessage(): Promise<string> {
        const message = await $(this.SELECTORS.permissionMessage);
        if (await message.isExisting()) {
            return await message.getText();
        }
        return '';
    }
    
    /**
     * Handle permission with automatic retry
     */
    static async handlePermissionWithRetry(
        action: () => Promise<void>,
        grantPermission: boolean = true,
        maxRetries: number = 3
    ): Promise<void> {
        let retries = 0;
        
        while (retries < maxRetries) {
            try {
                // Perform the action that triggers permission
                await action();
                
                // Check if permission dialog appeared
                if (await this.isPermissionDialogDisplayed()) {
                    if (grantPermission) {
                        await this.grantPermission();
                    } else {
                        await this.denyPermission();
                    }
                    
                    // Wait for dialog to disappear
                    await browser.pause(1000);
                }
                
                // Success
                return;
            } catch (error) {
                retries++;
                if (retries >= maxRetries) {
                    throw error;
                }
                console.log(`Permission handling attempt ${retries} failed, retrying...`);
                await browser.pause(1000);
            }
        }
    }
    
    /**
     * Reset app permissions (requires app reinstall)
     */
    static async resetPermissions(): Promise<void> {
        // This will be handled by appium:fullReset capability
        // or by using ADB commands
        await browser.execute('mobile: shell', {
            command: 'pm',
            args: ['clear', 'io.github.koo5.hillview']
        });
    }
    
    /**
     * Wait for and click camera button with retries
     */
    static async clickCameraButton(maxRetries: number = 3): Promise<void> {
        let retries = 0;
        
        while (retries < maxRetries) {
            try {
                const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
                
                // Wait for button to exist
                await cameraButton.waitForExist({ 
                    timeout: 10000,
                    timeoutMsg: 'Camera button not found'
                });
                
                // Ensure button is displayed
                await cameraButton.waitForDisplayed({ 
                    timeout: 5000,
                    timeoutMsg: 'Camera button not displayed'
                });
                
                // Small pause to ensure UI is stable
                await browser.pause(500);
                
                // Click the button
                await cameraButton.click();
                
                // Success
                return;
            } catch (error) {
                retries++;
                if (retries >= maxRetries) {
                    throw new Error(`Failed to click camera button after ${maxRetries} attempts: ${error}`);
                }
                console.log(`Camera button click attempt ${retries} failed, retrying...`);
                
                // Try to ensure app is in foreground
                await browser.execute('mobile: activateApp', { appId: 'io.github.koo5.hillview' });
                await browser.pause(2000);
            }
        }
    }
}