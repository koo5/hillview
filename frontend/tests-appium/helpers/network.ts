import { browser } from '@wdio/globals';

/**
 * Toggle the emulator's network connectivity. Uses the UiAutomator2
 * `mobile: setConnectivity` endpoint — the older `setNetworkConnection`
 * bitmask is rejected on modern Android, and the `svc wifi` shell fallback
 * needs Appium's --relaxed-security flag (not enabled here). The 2.5s
 * settle gives Kotlin's ConnectivityManager callback time to fire before
 * the next assertion.
 */
export async function setNetwork(online: boolean): Promise<void> {
    await (driver as any).execute('mobile: setConnectivity', {
        wifi: online,
        data: online,
    });
    await browser.pause(2500);
}
