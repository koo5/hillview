import type { Page } from '@playwright/test';

function isEnvFlagEnabled(value: string | undefined): boolean {
    return /^(1|true|yes|on)$/i.test(value?.trim() ?? '');
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
