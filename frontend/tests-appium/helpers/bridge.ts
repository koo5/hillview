import { browser } from '@wdio/globals';
import { ensureWebViewContext } from './selectors';

/**
 * Invoke a Tauri plugin command from the WebView and wait for it to settle.
 * Switches to the WebView context first. Resolves with the command result (or
 * `{ __err }` on failure / when the bridge isn't available).
 *
 * e.g. invokePlugin('plugin:hillview|tryUploads')
 *      invokePlugin('plugin:hillview|refresh_auth_token')
 */
export async function invokePlugin(command: string): Promise<unknown> {
    await ensureWebViewContext();
    return browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const cmd = arguments[0];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke(cmd).then(r => done(r), e => done({ __err: String(e) }));
    `, command);
}
