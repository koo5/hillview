import type { Page } from '@playwright/test';

function isEnvFlagEnabled(value: string | undefined): boolean {
    return /^(1|true|yes|on)$/i.test(value?.trim() ?? '');
}

/**
 * Filter expected/benign console errors (image loading, network errors, WebKit quirks).
 * Returns true if the error is unexpected and should be flagged.
 */
export function isUnexpectedError(text: string): boolean {
    // Firefox emits bare stack traces as separate console.error entries during
    // page transitions — just the call frames with no error message.
    if (text.trimStart().startsWith('Stack trace:')) return false;

    const expectedPatterns = [
        'favicon.ico',
        'ERR_NAME_NOT_RESOLVED',
        'Image load error',
        'Failed to load resource',
        'net::ERR_',
        'access control checks',   // WebKit blocks ES module loading in workers from Vite dev server
        'Worker error',            // consequence of the above in SimplePhotoWorker
        'establish a connection to the server',  // Firefox native EventSource connection error
        'getPosition',             // Leaflet invalidateSize during page navigation (Firefox)
        'invalidateSize',          // Leaflet resize race during page transition (Firefox)
    ];
    return !expectedPatterns.some(pattern => text.includes(pattern));
}

/**
 * Set up error collection on a page. Returns an object whose `errors` array
 * accumulates unexpected console errors throughout the test.
 *
 * Usage:
 *   const { errors } = collectErrors(page);
 *   // ... test actions ...
 *   expect(errors.length, `Found errors: ${errors.join(', ')}`).toBe(0);
 */
export function collectErrors(page: Page): { errors: string[] } {
    const errors: string[] = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error' && isUnexpectedError(msg.text())) {
            errors.push(msg.text());
        }
    });
    return { errors };
}

export function setupConsoleLogging(page: Page): void {
    // Only enable if the environment variable is set to a truthy value
    if (!isEnvFlagEnabled(process.env.PLAYWRIGHT_CONSOLE_LOG)) {
        return;
    }

    page.on('console', msg => {
        const msgType = msg.type();
        const text = msg.text();

        switch (msgType) {
            case 'error':
                console.log(`🔴 CONSOLE ERROR: ${text}`);
                break;
            case 'warning':
                console.log(`🟡 CONSOLE WARN: ${text}`);
                break;
            case 'info':
                console.log(`🔵 CONSOLE INFO: ${text}`);
                break;
            case 'debug':
                console.log(`🟢 CONSOLE DEBUG: ${text}`);
                break;
            default:
                console.log(`🔵 CONSOLE: ${text}`);
        }
    });

    // Also log uncaught exceptions and page errors
    page.on('pageerror', error => {
        console.log(`🔴 PAGE ERROR: ${error.message}`);
    });

    page.on('requestfailed', request => {
        console.log(`🔴 REQUEST FAILED: ${request.method()} ${request.url()} - ${request.failure()?.errorText}`);
    });
}
