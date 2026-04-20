import { browser } from '@wdio/globals';
import { spawn } from 'node:child_process';

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

/** Canonical emulator-console network speed profiles, fastest-first. */
export type NetworkSpeed = 'full' | 'lte' | 'hsdpa' | 'umts' | 'edge' | 'gprs' | 'gsm';

/**
 * Throttle the emulator's NIC via the emulator console. `adb emu network
 * speed <profile>` dials the upstream/downstream bandwidth of the virtual
 * NIC — the only way we have to actually slow down uploads (Chromedriver's
 * CDP throttling wouldn't affect the Kotlin upload path, and `mobile:
 * shell` is blocked by the project's Appium config). Runs from the host
 * process, so it sidesteps Appium entirely.
 *
 * Speeds:
 *   gsm  =  14.4 kbps down /  14.4 kbps up
 *   gprs =  40    kbps     /  40   kbps
 *   edge = 237    kbps     / 118   kbps
 *   ...
 *   full = unthrottled (default)
 */
export async function setNetworkSpeed(speed: NetworkSpeed): Promise<void> {
    await new Promise<void>((resolve, reject) => {
        const proc = spawn('adb', ['emu', 'network', 'speed', speed], {
            stdio: 'ignore',
        });
        proc.on('exit', (code) => {
            if (code === 0) resolve();
            else reject(new Error(`adb emu network speed ${speed} exited ${code}`));
        });
        proc.on('error', reject);
    });
    // The emulator needs a beat to reconfigure its NIC before the next
    // syscall observes the new throttle.
    await browser.pause(500);
}
