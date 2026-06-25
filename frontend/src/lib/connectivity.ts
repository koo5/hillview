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
