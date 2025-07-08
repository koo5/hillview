import { $ } from '@wdio/globals';

class AppPage {
    get mapContainer() {
        return $('[data-testid="map-container"]');
    }

    get cameraButton() {
        return $('[data-testid="camera-button"]');
    }

    get galleryButton() {
        return $('[data-testid="gallery-button"]');
    }

    get uploadButton() {
        return $('[data-testid="upload-button"]');
    }

    // Permission dialog elements
    get permissionDialog() {
        return $('//android.widget.LinearLayout[@resource-id="com.android.permissioncontroller:id/grant_dialog"]');
    }

    get permissionAllowButton() {
        return $('//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_button"]');
    }

    get permissionDenyButton() {
        return $('//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_deny_button"]');
    }

    get permissionAllowOnceButton() {
        return $('//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_one_time_button"]');
    }

    get permissionAllowAlwaysButton() {
        return $('//android.widget.Button[@resource-id="com.android.permissioncontroller:id/permission_allow_always_button"]');
    }

    get permissionMessage() {
        return $('//android.widget.TextView[@resource-id="com.android.permissioncontroller:id/permission_message"]');
    }

    // Alternative selectors for different Android versions
    get alternativeAllowButton() {
        return $('//android.widget.Button[contains(@text, "Allow") or contains(@text, "ALLOW")]');
    }

    get alternativeDenyButton() {
        return $('//android.widget.Button[contains(@text, "Deny") or contains(@text, "DENY")]');
    }

    get alternativeWhileUsingButton() {
        return $('//android.widget.Button[contains(@text, "While using") or contains(@text, "Only this time")]');
    }

    // Camera page elements
    get captureButton() {
        return $('//android.widget.Button[contains(@text, "Take Photo")]');
    }

    get locationInfo() {
        return $('//*[contains(@text, "Lat:") or contains(@text, "Location")]');
    }

    // Using XPath selectors for actual Android elements
    get cameraButtonXPath() {
        return $('//android.widget.Button[@text="Take photo"]');
    }

    get menuButtonXPath() {
        return $('//android.widget.Button[@text="Toggle menu"]');
    }

    get displayModeButtonXPath() {
        return $('//android.widget.Button[@text="Toggle display mode"]');
    }

    async waitForAppToLoad() {
        // Try data-testid first, fall back to XPath
        const exists = await this.mapContainer.isExisting();
        if (exists) {
            await this.mapContainer.waitForExist({ timeout: 10000 });
        } else {
            // Wait for WebView as fallback
            await $('android.webkit.WebView').waitForExist({ timeout: 10000 });
        }
    }

    async openCamera() {
        // Try data-testid first, fall back to XPath
        if (await this.cameraButton.isExisting()) {
            await this.cameraButton.click();
        } else {
            await this.cameraButtonXPath.click();
        }
    }

    async openGallery() {
        await this.galleryButton.click();
    }

    async isPermissionDialogDisplayed() {
        try {
            return await this.permissionDialog.isDisplayed();
        } catch {
            // Try alternative check
            return await this.alternativeAllowButton.isExisting();
        }
    }

    async getPermissionMessage() {
        if (await this.permissionMessage.isExisting()) {
            return await this.permissionMessage.getText();
        }
        return '';
    }

    async allowPermission(allowAlways = false) {
        if (allowAlways && await this.permissionAllowAlwaysButton.isExisting()) {
            await this.permissionAllowAlwaysButton.click();
        } else if (await this.alternativeWhileUsingButton.isExisting()) {
            await this.alternativeWhileUsingButton.click();
        } else if (await this.permissionAllowButton.isExisting()) {
            await this.permissionAllowButton.click();
        } else if (await this.alternativeAllowButton.isExisting()) {
            await this.alternativeAllowButton.click();
        }
    }

    async denyPermission() {
        if (await this.permissionDenyButton.isExisting()) {
            await this.permissionDenyButton.click();
        } else if (await this.alternativeDenyButton.isExisting()) {
            await this.alternativeDenyButton.click();
        }
    }
}

export default new AppPage();