import type { Page } from '@playwright/test';

export function setupConsoleLogging(page: Page): void {
    // Only enable if environment variable is set
    if (process.env.PLAYWRIGHT_CONSOLE_LOG !== 'true') {
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