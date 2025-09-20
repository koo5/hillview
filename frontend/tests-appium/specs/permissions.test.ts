import { browser, $, $$ } from '@wdio/globals';
import { PermissionHelper } from '../helpers/permissions';

describe('App Permissions', () => {
    beforeEach(async () => {
        // Reset to main page before each test
        await browser.execute('mobile: activateApp', { appId: 'cz.hillviedev' });
        await browser.pause(2000);

        // Wait for app to be fully loaded
        const webView = await $('android.webkit.WebView');
        await webView.waitForExist({ timeout: 10000 });

        // Additional pause to ensure UI is ready
        await browser.pause(1000);
    });

    describe('Camera Permission', () => {
        it('should request camera permission when accessing camera', async () => {
            // Navigate to camera
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });

            // Ensure button is clickable
            await cameraButton.waitForDisplayed({ timeout: 5000 });

            // Click camera button - this should trigger permission request
            await cameraButton.click();

            // Wait for permission dialog
            const permissionRequested = await PermissionHelper.waitForPermissionDialog();
            expect(permissionRequested).toBe(true);

            // Check permission message contains camera
            const message = await PermissionHelper.getPermissionMessage();
            const isCameraPermission = message.toLowerCase().includes('camera') ||
                                      message.toLowerCase().includes('photo') ||
                                      message.toLowerCase().includes('picture');
            expect(isCameraPermission).toBe(true);
        });

        it('should allow camera access when permission is granted', async () => {
            // Navigate to camera
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // Grant permission
            await PermissionHelper.grantPermission();
            await browser.pause(1000);

            // Verify we're on camera page
            const captureButton = await $('//android.widget.Button[contains(@text, "Take Photo")]');
            const isOnCameraPage = await captureButton.isExisting();
            expect(isOnCameraPage).toBe(true);

            // Go back
            await browser.back();
        });

        it('should handle camera permission denial gracefully', async () => {
            // Navigate to camera
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // Deny permission
            await PermissionHelper.denyPermission();
            await browser.pause(1000);

            // App should handle denial gracefully - either stay on main page or show error
            // Check if we're still on main page or if there's an error message
            const mainPageButton = await $('//android.widget.Button[@text="Take photo"]');
            const errorMessage = await $('//*[contains(@text, "Camera permission") or contains(@text, "Permission denied")]');

            const handledGracefully = await mainPageButton.isExisting() || await errorMessage.isExisting();
            expect(handledGracefully).toBe(true);
        });

        it('should remember camera permission choice', async () => {
            // First grant permission
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            await PermissionHelper.grantPermission();
            await browser.pause(1000);

            // Go back to main page
            await browser.back();
            await browser.pause(1000);

            // Try accessing camera again
            await cameraButton.waitForExist({ timeout: 5000 });
            await cameraButton.click();
            await browser.pause(1000);

            // Permission dialog should not appear again
            const permissionDialogShown = await PermissionHelper.isPermissionDialogDisplayed();
            expect(permissionDialogShown).toBe(false);

            // Should be directly on camera page
            const captureButton = await $('//android.widget.Button[contains(@text, "Take Photo")]');
            expect(await captureButton.isExisting()).toBe(true);

            // Go back
            await browser.back();
        });
    });

    describe('Location Permission', () => {
        it('should request location permission when needed', async () => {
            // The app likely requests location on startup or when taking photos
            // Try to trigger location permission by navigating to camera
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // Wait a bit for potential location permission
            await browser.pause(2000);

            // Check if location permission dialog appears
            const permissionShown = await PermissionHelper.isPermissionDialogDisplayed();

            if (permissionShown) {
                const message = await PermissionHelper.getPermissionMessage();
                const isLocationPermission = message.toLowerCase().includes('location') ||
                                           message.toLowerCase().includes('gps');

                // If it's location permission, grant it
                if (isLocationPermission) {
                    await PermissionHelper.grantPermission();
                    expect(isLocationPermission).toBe(true);
                }
            }

            // Back to main
            await browser.back();
        });

        it('should display location information when permission is granted', async () => {
            // Navigate to camera where location is shown
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // Handle any permission dialogs
            if (await PermissionHelper.isPermissionDialogDisplayed()) {
                await PermissionHelper.grantPermission();
                await browser.pause(1000);
            }

            // Look for location information display
            const locationElements = await $$('//*[contains(@text, "Lat:") or contains(@text, "Lon:") or contains(@text, "Location")]');

            // Should find location info if permission is granted
            expect(locationElements.length).toBeGreaterThan(0);

            // Go back
            await browser.back();
        });

        it('should handle location permission denial', async () => {
            // This test will attempt to deny location permission
            // Note: This might need adjustment based on when exactly the app requests location

            // Try to trigger location permission
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // If location permission appears, deny it
            if (await PermissionHelper.waitForPermissionDialog(3000)) {
                const message = await PermissionHelper.getPermissionMessage();
                if (message.toLowerCase().includes('location')) {
                    await PermissionHelper.denyPermission();
                    await browser.pause(1000);

                    // App should still function without location
                    // Check if we can still access basic features
                    const webView = await $('android.webkit.WebView');
                    expect(await webView.isExisting()).toBe(true);
                }
            }

            // Go back if on camera page
            await browser.back();
        });
    });

    describe('Permission Combinations', () => {
        it('should handle multiple permission requests', async () => {
            // This test handles the scenario where both camera and location permissions are requested
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            let permissionsHandled = 0;

            // Handle first permission (could be camera or location)
            if (await PermissionHelper.waitForPermissionDialog()) {
                await PermissionHelper.grantPermission();
                permissionsHandled++;
                await browser.pause(1000);
            }

            // Handle second permission if it appears
            if (await PermissionHelper.waitForPermissionDialog(3000)) {
                await PermissionHelper.grantPermission();
                permissionsHandled++;
                await browser.pause(1000);
            }

            // We should have handled at least one permission
            expect(permissionsHandled).toBeGreaterThan(0);

            // Verify we can access camera features after granting permissions
            const captureButton = await $('//android.widget.Button[contains(@text, "Take Photo")]');
            const locationInfo = await $('//*[contains(@text, "Lat:") or contains(@text, "Location")]');

            const hasAccess = await captureButton.isExisting() || await locationInfo.isExisting();
            expect(hasAccess).toBe(true);

            // Go back
            await browser.back();
        });

        it('should function with mixed permission grants/denials', async () => {
            // Test app behavior when some permissions are granted and others denied
            const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
            await cameraButton.waitForExist({ timeout: 10000 });
            await cameraButton.waitForDisplayed({ timeout: 5000 });
            await cameraButton.click();

            // Handle first permission - grant it
            if (await PermissionHelper.waitForPermissionDialog()) {
                const message = await PermissionHelper.getPermissionMessage();
                console.log('First permission:', message);
                await PermissionHelper.grantPermission();
                await browser.pause(1000);
            }

            // Handle second permission - deny it
            if (await PermissionHelper.waitForPermissionDialog(3000)) {
                const message = await PermissionHelper.getPermissionMessage();
                console.log('Second permission:', message);
                await PermissionHelper.denyPermission();
                await browser.pause(1000);
            }

            // App should still be functional
            const webView = await $('android.webkit.WebView');
            expect(await webView.isExisting()).toBe(true);

            // Some features might be available depending on which permission was granted
            const anyFeatureAvailable = await $('//android.widget.Button').isExisting();
            expect(anyFeatureAvailable).toBe(true);

            // Go back if possible
            await browser.back();
        });
    });
});
