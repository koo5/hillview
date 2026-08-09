import { get } from 'svelte/store';
import { invoke } from '@tauri-apps/api/core';
import type { TokenManager, TokenData } from './tokenManager';
import { TokenRefreshError } from './tokenManager';
import { auth } from './authStore';
import { logout, getAuthGeneration } from './auth.svelte';
import { kotlinMessageQueue } from './KotlinMessageQueue';
import { addAlert } from './alertSystem.svelte';

/** Native session snapshot returned by the get_session_state cmd. */
interface NativeSessionState {
    has_access_token: boolean;
    has_valid_access_token: boolean;
    has_refresh_token: boolean;
    expires_at: string | null;
    expired: boolean;
    expired_at?: number;
    expired_reason?: string;
}

/**
 * Android Token Manager
 *
 * Delegates all token operations to the Android plugin, which handles
 * refresh logic with mutex protection to prevent race conditions.
 */
export class AndroidTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🢄🔐[ANDROID_TOKEN_MGR]';
    private lastReconcileAt = 0;

    constructor() {
        this.setupSessionExpiryHandler();
        this.setupSessionReconciler();
    }

    /**
     * Native clears the session when the server rejects the refresh token (401) and
     * enqueues an "auth-expired" message via the durable Kotlin→JS message queue
     * (polled), NOT a fire-and-forget Tauri event. The queue survives the case where
     * the 401 happens while the app is backgrounded with no WebView — the message
     * waits and is delivered when the WebView next polls. We then log out in lockstep
     * so the JS auth store and native token state don't diverge (otherwise the UI stays
     * "authenticated" while native has no tokens). Re-checks current tokens first so a
     * re-login that already replaced the session isn't torn down by a stale message
     * from the previous one.
     */
    private setupSessionExpiryHandler(): void {
        if (!kotlinMessageQueue) {
            console.warn(`${this.LOG_PREFIX} 🔐➡️ kotlinMessageQueue unavailable; cannot register 'auth-expired' handler`);
            return;
        }
        console.log(`${this.LOG_PREFIX} 🔐➡️ Registering 'auth-expired' message-queue handler`);
        kotlinMessageQueue.on('auth-expired', async () => {
            // Snapshot at receipt, BEFORE any await: if a re-login bumps the auth
            // generation while we re-check the token, the stale-tagged logout below is
            // suppressed by logout()'s guard — the same deterministic protection the web
            // path uses, closing the TOCTOU the getValidToken() re-check alone can't.
            const generation = getAuthGeneration();
            console.warn(`${this.LOG_PREFIX} 🔐➡️ Received 'auth-expired' from native message queue (gen ${generation})`);
            try {
                // Re-check: if a re-login already replaced the session, native now has a
                // valid token — don't tear it down over the old 401.
                const token = await this.getValidToken();
                if (token) {
                    console.log(`${this.LOG_PREFIX} 🔐➡️ Native has a valid token again (re-login?); ignoring stale auth-expired`);
                    return;
                }
                console.warn(`${this.LOG_PREFIX} 🔐➡️ No valid token; logging out JS in lockstep with native`);
                // In-app explanation to pair with the system notification —
                // the user shouldn't just find themselves on /login untold.
                addAlert('Your session has expired — please log in again.', 'warning', {
                    priority: 8,
                    duration: 0,
                    source: 'session_expired',
                });
                logout('Session expired (native)', { generation });
            } catch (error) {
                console.error(`${this.LOG_PREFIX} 🔐➡️ Error handling 'auth-expired':`, error);
            }
        });
        console.log(`${this.LOG_PREFIX} 🔐➡️ 'auth-expired' message-queue handler registered`);
    }

    /**
     * LEVEL-triggered reconciliation, complementing the EDGE-triggered queue
     * message above. The queue message lives in plugin-instance memory: it is
     * lost if the process dies (or the WebView isn't polling) between the
     * native session death and delivery — historically leaving the JS auth
     * store showing "authenticated" against a dead session forever, because
     * token-less requests never trip http.ts's 401-logout path. So instead of
     * relying on catching the event, periodically re-derive: ask native for
     * its persisted session state and correct the JS store to match. Runs at
     * startup (once the initial auth check settles), on every return to
     * foreground, and after a forced refresh comes back empty (post-401).
     */
    private setupSessionReconciler(): void {
        // Startup: wait for the auth store's initial check to settle so we
        // reconcile against the real is_authenticated, not its boot default.
        let startupDone = false;
        const unsubscribe = auth.subscribe((s) => {
            if (!s.checked || startupDone) return;
            startupDone = true;
            // Defer the unsubscribe: this callback can fire synchronously
            // during subscribe(), before `unsubscribe` is assigned.
            setTimeout(() => unsubscribe(), 0);
            void this.reconcileSessionState('startup');
        });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                void this.reconcileSessionState('resume');
            }
        });
    }

    /** Fetch the native session snapshot (optionally acknowledging the expired flag). */
    private async getNativeSessionState(consumeExpired: boolean): Promise<NativeSessionState> {
        return await invoke('plugin:hillview|cmd', {
            command: 'get_session_state',
            params: { consume_expired: consumeExpired },
        }) as NativeSessionState;
    }

    /**
     * Reconcile the JS auth store against native session state:
     *  - native says the session DIED involuntarily (persisted flag) → surface
     *    it in-app and, if JS still thinks it's authenticated, log out (which
     *    navigates to /login). The flag is consumed on read so it surfaces once.
     *  - native has NO session at all while JS thinks it's authenticated
     *    (event lost, or cleared by another context) → log out quietly.
     * Guarded by the auth generation so a login that lands mid-reconcile is
     * never torn down by a stale conclusion.
     */
    async reconcileSessionState(trigger: string): Promise<void> {
        const now = Date.now();
        if (now - this.lastReconcileAt < 5000) return;
        this.lastReconcileAt = now;

        // Snapshot BEFORE any await (same TOCTOU protection as the queue handler).
        const generation = getAuthGeneration();
        const jsAuthenticated = get(auth).is_authenticated;

        try {
            const state = await this.getNativeSessionState(true);

            if (state.expired) {
                const reason = state.expired_reason || 'unknown';
                console.warn(`${this.LOG_PREFIX} 🔐⇄ Reconcile(${trigger}): native session expired (${reason}); JS authenticated=${jsAuthenticated}`);
                // Surface when it's news: the UI still shows authenticated, or the
                // app just started (the death happened in a previous process life —
                // the user deserves to know why they're logged out). A mid-session
                // resume-reconcile on an already-logged-out UI adds nothing.
                if (jsAuthenticated || trigger === 'startup') {
                    addAlert('Your session has expired — please log in again.', 'warning', {
                        priority: 8,
                        duration: 0, // persistent: expiry is actionable, don't let it slip by
                        source: 'session_expired',
                    });
                }
                if (jsAuthenticated) {
                    await logout(`Session expired (native, reconciled on ${trigger}: ${reason})`, { generation });
                }
                return;
            }

            if (jsAuthenticated && !state.has_access_token && !state.has_refresh_token) {
                console.warn(`${this.LOG_PREFIX} 🔐⇄ Reconcile(${trigger}): JS authenticated but native has no session; logging out`);
                await logout(`Session absent (native, reconciled on ${trigger})`, { generation });
            }
        } catch (error) {
            // Reconciliation is a safety net — never let it break the caller.
            console.error(`${this.LOG_PREFIX} 🔐⇄ Reconcile(${trigger}) failed:`, error);
        }
    }

    async getValidToken(force: boolean = false): Promise<string | null> {
        // console.log(`${this.LOG_PREFIX} Getting valid token from Android (force: ${force})`);

        try {
            // Android plugin handles token validation and refresh internally
            const result = await invoke('plugin:hillview|get_auth_token', { force }) as {
                token: string | null;
                expires_at: string | null;
                success: boolean;
                error?: string;
            };

            if (!result.success) {
                console.log(`${this.LOG_PREFIX} Android reports no valid token: ${result.error}`);
                if (force) void this.reconcileSessionState('post-401');
                return null;
            }

            if (result.token) {
                // console.log(`${this.LOG_PREFIX} Valid token received from Android`);
                return result.token;
            }

            console.log(`${this.LOG_PREFIX} No token available`);
            // force=true means a SENT token was just rejected server-side; coming
            // back empty after the forced refresh is exactly the moment the native
            // session may have died — reconcile so the UI doesn't linger stale.
            if (force) void this.reconcileSessionState('post-401');
            return null;
        } catch (err) {
            console.error(`${this.LOG_PREFIX} Failed to get valid token:`, err);
            if (force) void this.reconcileSessionState('post-401');
            return null;
        }
    }

    async refreshToken(): Promise<boolean> {
        try {
            // console.log(`${this.LOG_PREFIX} Requesting token refresh from Android`);

            const result = await invoke('plugin:hillview|refresh_auth_token') as {
                success: boolean;
                error?: string;
            };

            if (result.success) {
                // console.log(`${this.LOG_PREFIX} Token refresh successful`);
                return true;
            } else {
                console.log(`${this.LOG_PREFIX} Token refresh failed: ${result.error}`);
                return false;
            }

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error refreshing token:`, error);
            throw new TokenRefreshError(`Android token refresh failed: ${error}`);
        }
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
        try {
            // console.log(`${this.LOG_PREFIX} Storing tokens in Android`);
            // console.log(`${this.LOG_PREFIX} - Token data:`, JSON.stringify({
            //     hasAccessToken: !!tokenData.access_token,
            //     hasRefreshToken: !!tokenData.refresh_token,
            //     expiresAt: tokenData.expires_at,
            //     refreshTokenExpiresAt: tokenData.refresh_token_expires_at
            // }));

            // console.log(`${this.LOG_PREFIX} - Calling plugin with:`, JSON.stringify({
            //     token: tokenData.access_token ? 'present' : 'missing',
            //     refreshToken: tokenData.refresh_token ? 'present' : 'missing',
            //     expiresAt: tokenData.expires_at,
            //     refreshExpiry: tokenData.refresh_token_expires_at
            // }));

            const result = await invoke('plugin:hillview|store_auth_token', {
                token: tokenData.access_token,
                refresh_token: tokenData.refresh_token,
                // Forwarded to native as-is: it must stay a Z-terminated ISO-8601 instant.
                // The Kotlin side parses it with Java ISO_INSTANT, which rejects a "+00:00"
                // offset. Backend token responses (response_model=Token) already emit the
                // Z form — don't reformat it here.
                expires_at: tokenData.expires_at,
                refresh_expiry: tokenData.refresh_token_expires_at
            }) as { success: boolean; error?: string };

            if (!result.success) {
                const errorMsg = result.error || 'Unknown error storing tokens';
                console.error(`${this.LOG_PREFIX} Plugin returned error: ${errorMsg}`);
                throw new Error(`${errorMsg}`);
            }

            // console.log(`${this.LOG_PREFIX} Tokens stored successfully in Android`);

            // Update auth store - tokens stored means authenticated
            auth.update(state => ({
                ...state,
                is_authenticated: true
            }));

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error storing tokens in Android:`, error);
            throw error;
        }
    }

    async clearTokens(): Promise<void> {
        try {
            // console.log(`${this.LOG_PREFIX} Clearing tokens in Android`);

            await invoke('plugin:hillview|clear_auth_token');

            // console.log(`${this.LOG_PREFIX} Tokens cleared successfully from Android`);

            // Update auth store - no tokens means not authenticated
            auth.update(state => ({
                ...state,
                is_authenticated: false,
                user: null
            }));

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error clearing tokens from Android:`, error);
            throw error;
        }
    }

    async isTokenExpired(bufferMinutes: number = 2): Promise<boolean> {
        try {
            const result = await invoke('plugin:hillview|is_token_expired', {
                buffer_minutes: bufferMinutes
            }) as { expired: boolean };

            return result.expired;
        } catch (err) {
            console.error(`${this.LOG_PREFIX} Failed to check token expiry:`, err);
            return true; // Assume expired on error for safety
        }
    }

    async registerClientPublicKey(): Promise<void> {
        // Client key registration is now handled automatically by Android during token storage
        // console.log(`${this.LOG_PREFIX} Client public key registration handled automatically by Android`);
    }

}
