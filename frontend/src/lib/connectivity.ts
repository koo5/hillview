import { addAlert, removeAlertsBySource } from './alertSystem.svelte';
import { backendUrl } from './config';

/**
 * Run `handler` when the app likely regains connectivity — the network comes back
 * online, or the tab becomes visible again (e.g. after the device wakes from sleep).
 * Returns a cleanup function that removes the listeners. No-op outside the browser.
 */
export function onReconnect(handler: () => void): () => void {
    if (typeof window === 'undefined') return () => {};

    const onVisible = () => {
        if (document.visibilityState === 'visible') handler();
    };

    window.addEventListener('online', handler);
    document.addEventListener('visibilitychange', onVisible);

    return () => {
        window.removeEventListener('online', handler);
        document.removeEventListener('visibilitychange', onVisible);
    };
}

// ── Connectivity episodes ───────────────────────────────────────────────────
// One outage EPISODE = one soft, persistent "Reconnecting…" alert — never a
// hard error, because the common trigger is benign: at phone-wake the first
// requests routinely fail for a few seconds while Android re-attaches the
// network. The episode starts on the first network-level fetch failure
// (reported by http.ts), is kept honest by a cheap /debug probe loop plus an
// immediate probe on wake/online, and ends — clearing the alert — the moment
// ANY request reaches the server: a page retry, the probe, or the auth
// reconciler, whichever comes first. Page-level feedback (spinners, per-page
// error states with retry) stays the pages' responsibility; this is only the
// global "the network is the problem and we're on it" signal.

const PROBE_INTERVAL_MS = 5000;

let connectivityLost = false;
let probeTimer: ReturnType<typeof setTimeout> | null = null;
let wakeProbeWired = false;

/** A request failed at the network level — open (or continue) an outage episode. */
export function reportConnectivityLoss(): void {
    if (typeof window === 'undefined' || connectivityLost) return;
    connectivityLost = true;
    addAlert('Reconnecting…', 'warning', {
        priority: 6,
        duration: 0, // persists exactly as long as the episode does
        source: 'connectivity',
    });
    if (!wakeProbeWired) {
        wakeProbeWired = true;
        onReconnect(() => {
            if (connectivityLost) void probeBackend();
        });
    }
    scheduleProbe();
}

/** A request reached the server (any HTTP status) — close the episode. */
export function reportConnectivityRestored(): void {
    if (!connectivityLost) return;
    connectivityLost = false;
    if (probeTimer) {
        clearTimeout(probeTimer);
        probeTimer = null;
    }
    removeAlertsBySource('connectivity');
}

function scheduleProbe(): void {
    if (probeTimer) return;
    probeTimer = setTimeout(() => {
        probeTimer = null;
        void probeBackend();
    }, PROBE_INTERVAL_MS);
}

async function probeBackend(): Promise<void> {
    if (!connectivityLost) return;
    try {
        // Any resolution — even a 5xx — means the server is reachable; fetch
        // rejects only on network-level failure.
        await fetch(`${backendUrl}/debug`, { cache: 'no-store' });
        reportConnectivityRestored();
    } catch {
        scheduleProbe();
    }
}
