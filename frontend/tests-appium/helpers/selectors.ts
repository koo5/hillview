import { $, $$ } from '@wdio/globals';

const WEBVIEW_CONTEXT = 'WEBVIEW_cz.hillviedev';
const NATIVE_CONTEXT = 'NATIVE_APP';

/**
 * Ensure we're in WebView context for CSS/data-testid selectors.
 */
export async function ensureWebViewContext(): Promise<void> {
    const ctx = await driver.getContext();
    if (ctx !== WEBVIEW_CONTEXT) {
        const contexts = await driver.getContexts();
        const webview = contexts.find((c: string) => c.includes('WEBVIEW'));
        if (webview) {
            await driver.switchContext(webview as string);
        } else {
            throw new Error('No WebView context available');
        }
    }
}

/**
 * Ensure we're in native context for Android system dialogs.
 */
export async function ensureNativeContext(): Promise<void> {
    const ctx = await driver.getContext();
    if (ctx !== NATIVE_CONTEXT) {
        await driver.switchContext(NATIVE_CONTEXT);
    }
}

/**
 * Find a single element by data-testid (switches to WebView context).
 */
export async function byTestId(testId: string): Promise<WebdriverIO.Element> {
    await ensureWebViewContext();
    return $(`[data-testid="${testId}"]`);
}

/**
 * Find multiple elements by data-testid (switches to WebView context).
 */
export async function allByTestId(testId: string): Promise<WebdriverIO.ElementArray> {
    await ensureWebViewContext();
    return $$(`[data-testid="${testId}"]`);
}

/**
 * Open the navigation menu from any page. The map uses Main.svelte's
 * `hamburger-menu`; other pages (/settings, /photos, etc.) use
 * StandardHeader's `header-menu-button`. Picks whichever is present.
 * Mirrors the Playwright openMenu helper in tests-playwright/navigation-menu.spec.ts.
 */
export async function openMenu(): Promise<void> {
    await ensureWebViewContext();
    const btn = await $(`[data-testid="header-menu-button"], [data-testid="hamburger-menu"]`);
    await btn.waitForDisplayed({ timeout: 15000 });
    await btn.click();
}

/**
 * Find a native Android element by text (for system dialogs, permissions, etc.).
 * Switches to native context first.
 */
export async function nativeByText(text: string): Promise<WebdriverIO.Element> {
    await ensureNativeContext();
    return $(`android=new UiSelector().text("${text}")`);
}

/**
 * Find a native Android element by partial text.
 */
export async function nativeByTextContains(text: string): Promise<WebdriverIO.Element> {
    await ensureNativeContext();
    return $(`android=new UiSelector().textContains("${text}")`);
}

/**
 * Find a native Android element by content description (accessibility ID).
 * Useful for WebView elements when you can't switch to WebView context.
 */
export async function nativeByDesc(desc: string): Promise<WebdriverIO.Element> {
    await ensureNativeContext();
    return $(`~${desc}`);
}

/**
 * Accept Android permission dialogs (camera, location, etc.).
 * Tries common permission button texts. Safe to call when no dialog is showing.
 */
export async function acceptPermissionDialogIfPresent(
    /** Max time (ms) to wait for a dialog to appear before giving up. */
    timeout = 5000,
): Promise<boolean> {
    await ensureNativeContext();
    const buttonTexts = ['While using the app', 'Only this time', 'Allow'];
    const deadline = Date.now() + timeout;

    while (Date.now() < deadline) {
        for (const text of buttonTexts) {
            try {
                const btn = await $(`android=new UiSelector().text("${text}")`);
                if (await btn.isDisplayed()) {
                    await btn.click();
                    await driver.pause(1000);
                    return true;
                }
            } catch {
                // button not found, try next
            }
        }
        await driver.pause(500);
    }
    return false;
}

/** Well-known data-testid values from the Svelte frontend */
export const TESTID = {
    // Main.svelte toolbar
    hamburgerMenu: 'hamburger-menu',
    cameraButton: 'camera-button',
    linesButton: 'lines-button',
    nativeCameraBtn: 'native-camera-btn',

    // Map.svelte navigation
    rotateCcw: 'rotate-ccw-btn',
    rotateCw: 'rotate-cw-btn',
    moveForward: 'move-forward-btn',
    moveBackward: 'move-backward-btn',
    trackLocation: 'track-location-btn',
    zoomIn: 'zoom-in-btn',
    zoomOut: 'zoom-out-btn',
    showAll: 'show-all-button',
    filters: 'filters-button',

    // CompassButton.svelte
    compassButton: 'compass-button',
    compassModeMenu: 'compass-mode-menu',
    walkingModeOption: 'walking-mode-option',
    carModeOption: 'car-mode-option',

    // BearingStateArrow.svelte — has `aria-valuenow` carrying current bearingDeg.
    bearingArrowHitarea: 'bearing-arrow-hitarea',

    // CameraCapture.svelte
    allowCameraBtn: 'allow-camera-btn',

    // NavigationMenu.svelte
    settingsMenuLink: 'settings-menu-link',

    // UploadSettings.svelte
    autoUploadEnabled: 'auto-upload-enabled',
    autoUploadDisabled: 'auto-upload-disabled',
    autoUploadDisabledNever: 'auto-upload-disabled-never',
    wifiOnlyCheckbox: 'wifi-only-checkbox',

    // StorageSettings.svelte
    storagePublicFolder: 'storage-public-folder',
    storagePrivateFolder: 'storage-private-folder',
    storageMediaStoreApi: 'storage-mediastore-api',

    // settings/+page.svelte sub-nav
    advancedMenuLink: 'advanced-menu-link',

    // settings/advanced/+page.svelte
    geoTrackingExportButton: 'geo-tracking-export-button',
    geoTrackingAutoExportCheckbox: 'geo-tracking-auto-export-checkbox',

    // LicenseSelector.svelte
    licenseCheckbox: 'license-checkbox',

    // CompassSettings.svelte — writes to compassPrefs via the same set_settings
    // Kotlin handler that owns the upload prefs, so it's useful for cross-category
    // merge coverage.
    landscapeArmor22Checkbox: 'landscape-armor22-checkbox',
} as const;
