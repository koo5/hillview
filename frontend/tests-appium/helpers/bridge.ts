import { browser } from '@wdio/globals';
import { ensureWebViewContext } from './selectors';

/**
 * Invoke a Tauri plugin command from the WebView and wait for it to settle.
 * Switches to the WebView context first. Resolves with the command result (or
 * `{ __err }` on failure / when the bridge isn't available).
 *
 * e.g. invokePlugin('plugin:hillview|tryUploads')
 *      invokePlugin('plugin:hillview|refresh_auth_token')
 *      invokePlugin('plugin:hillview|cmd', { command: 'set_settings', params: {...} })
 */
export async function invokePlugin(command: string, args?: Record<string, unknown>): Promise<unknown> {
    await ensureWebViewContext();
    // The command result is wrapped under __ok before crossing the WebDriver
    // boundary: wdio treats ANY execute/async response whose top-level value has
    // an `error` key as a protocol error and throws (then retries, re-firing the
    // command). Plugin payloads like {success: false, error: "Token refresh
    // failed"} are legitimate results and must not surface at the top level.
    const res = (await browser.executeAsync(`
        const done = arguments[arguments.length - 1];
        const cmd = arguments[0];
        const cmdArgs = arguments[1];
        const invoke = window.__TAURI_INTERNALS__ && window.__TAURI_INTERNALS__.invoke;
        if (!invoke) { done({ __err: 'no invoke' }); return; }
        invoke(cmd, cmdArgs ?? undefined).then(r => done({ __ok: r }), e => done({ __err: String(e) }));
    `, command, args ?? null)) as Record<string, unknown> | null;
    return res && typeof res === 'object' && '__ok' in res ? res.__ok : res;
}
