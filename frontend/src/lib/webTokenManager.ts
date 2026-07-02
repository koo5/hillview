import { get } from 'svelte/store';
import type { TokenManager, TokenData } from './tokenManager';
import { TokenExpiredError, TokenRefreshError } from './tokenManager';
import { backendUrl } from './config';
import { auth } from './authStore';
import { logout, fetchUserData, getAuthGeneration, bumpAuthGeneration } from './auth.svelte';
import { clientCrypto } from './clientCrypto';
import { http } from '$lib/http';
import { authStorage, type IndexedDbTokenData } from './browser/authStorage';
import { onReconnect } from './connectivity';

const doLog = false;

/**
 * Web Token Manager
 *
 * Handles token management for web-only environments using IndexedDB.
 * Single source of truth with cross-tab reactivity via BroadcastChannel.
 * Implements race condition protection through promise deduplication.
 */
export class WebTokenManager implements TokenManager {
    private readonly LOG_PREFIX = '🔐[WEB_TOKEN_MGR]';
    private refreshPromise: Promise<TokenData> | null = null;

    // Local cache to avoid async reads on every token access
    private cachedTokenData: IndexedDbTokenData | null = null;
    private cacheInitialized = false;

    constructor() {
        // Subscribe to cross-tab auth changes
        authStorage.onAuthChange(async () => {
            console.log(`${this.LOG_PREFIX} Auth changed in another tab, refreshing cache`);
            const hadTokens = !!this.cachedTokenData;
            await this.refreshCache();

            // Update auth store based on new token state
            if (this.cachedTokenData) {
                auth.update(state => ({ ...state, is_authenticated: true }));
                // If we just gained tokens (login in another tab), fetch user data
                if (!hadTokens) {
                    console.log(`${this.LOG_PREFIX} Detected new login, fetching user data`);
                    // A login synced from another tab establishes a new session here
                    // too — bump the generation so a stale in-flight request in this
                    // tab can't log out the freshly-synced session (mirrors
                    // completeAuthentication).
                    bumpAuthGeneration();
					fetchUserData();
                }
            } else {
                auth.update(state => ({ ...state, is_authenticated: false, user: null, userStatus: 'idle' }));
            }
        });

        this.setupConnectivityRecovery();
    }

    /**
     * When connectivity returns (network back online) or the tab becomes visible
     * again, proactively refresh an expired token so a stale tab heals itself
     * instead of waiting for the next user action. Guarded so it only touches the
     * network when there is a session and the token actually needs refreshing.
     */
    private setupConnectivityRecovery(): void {
        onReconnect(() => void this.recoverSessionIfNeeded('reconnect'));
    }

    private async recoverSessionIfNeeded(trigger: string): Promise<void> {
        // A refresh is already running, or there's nothing to recover.
        if (this.refreshPromise) return;
        if (!this.cacheInitialized || !this.cachedTokenData) return;

        // Only act when the token is actually expired or the refresh token is due
        // for proactive renewal — don't hit the network on every tab focus.
        const needsRefresh = (await this.isTokenExpired()) || (await this.shouldRenewRefreshToken());
        if (!needsRefresh || this.refreshPromise) return;

        console.log(`${this.LOG_PREFIX} Connectivity recovery (${trigger}): token needs refresh, attempting`);
        try {
            const token = await this.getValidToken();
            // Healed, but the user record is missing (e.g. the session was half torn
            // down earlier) — refetch so gated views (e.g. /photos) recover too.
            if (token && !get(auth).user) {
                fetchUserData();
            }
        } catch {
            // Terminal failure already logged out via getValidToken; a transient one
            // returns null and keeps the session for the next reconnect event.
        }
    }

    // Initialize cache from IndexedDB (call once on app startup)
    async init(): Promise<void> {
        if (this.cacheInitialized) return;
        await this.refreshCache();
        this.cacheInitialized = true;
    }

    private async refreshCache(): Promise<void> {
        this.cachedTokenData = await authStorage.getTokenData();
    }

    private async ensureCacheInitialized(): Promise<void> {
        if (!this.cacheInitialized) {
            await this.init();
        }
    }

    async getValidToken(force: boolean = false): Promise<string | null> {
        // Snapshot the auth generation at the start of this token request so a
        // logout triggered by a refresh failure here is ignored if a newer login
        // has replaced the session in the meantime (see logout()).
        const requestAuthGeneration = getAuthGeneration();
        try {
            await this.ensureCacheInitialized();

            // If refresh is already in progress, wait for it
            if (this.refreshPromise) {
                if (doLog) console.log(`${this.LOG_PREFIX} Refresh in progress, waiting...`);
                try {
                    const newToken = await this.refreshPromise;
                    return newToken.access_token;
                } catch (error) {
                    console.warn(`${this.LOG_PREFIX} Refresh failed:`, error);
                    return null;
                }
            }

            if (!this.cachedTokenData) {
                if (doLog) console.log(`${this.LOG_PREFIX} No token available`);
                return null;
            }

            // Check if token is expired OR refresh token needs proactive renewal OR force refresh
            const tokenExpired = await this.isTokenExpired();
            const needsRefreshRenewal = await this.shouldRenewRefreshToken();

            if (force || tokenExpired || needsRefreshRenewal) {
                if (force) {
                    console.log(`${this.LOG_PREFIX} Force refresh requested (e.g., after 401)`);
                } else if (tokenExpired) {
                    console.log(`${this.LOG_PREFIX} Token expired, attempting refresh`);
                } else {
                    console.log(`${this.LOG_PREFIX} Refresh token expiring soon, proactive renewal`);
                }

                this.refreshPromise = this.performRefresh(force);

                try {
                    const newToken = await this.refreshPromise;
                    this.refreshPromise = null;
                    return newToken.access_token;
                } catch (error) {
                    this.refreshPromise = null;

                    // Transient failure (timeout / network / 5xx): the refresh token is
                    // still valid and the tokens are kept. Don't tear down the session
                    // over a connectivity blip — return null so the caller surfaces a
                    // connection error and a later attempt / reconnect can succeed.
                    // AuthStatusWatcher already shows a "check your connection / retry"
                    // prompt via refresh_status: 'failed'.
                    if (error instanceof TokenRefreshError && error.transient) {
                        console.warn(`${this.LOG_PREFIX} Refresh failed transiently; keeping session:`, error);
                        return null;
                    }

                    // Terminal failure (refresh token rejected / expired): log out.
                    console.warn(`${this.LOG_PREFIX} Refresh failed:`, error);
                    logout('Token refresh failed', { generation: requestAuthGeneration });
                    throw new TokenExpiredError('Token expired and refresh failed');
                }
            }

            return this.cachedTokenData.access_token;

        } catch (error) {
            if (error instanceof TokenExpiredError) {
                throw error;
            }
            console.error(`${this.LOG_PREFIX} Error getting valid token:`, error);
            return null;
        }
    }

    async refreshToken(): Promise<boolean> {
        try {
            console.log(`${this.LOG_PREFIX} Manual token refresh requested`);

            if (this.refreshPromise) {
                console.log(`${this.LOG_PREFIX} Refresh already in progress, waiting...`);
                await this.refreshPromise;
                return true;
            }

            this.refreshPromise = this.performRefresh();
            await this.refreshPromise;
            this.refreshPromise = null;

            return true;

        } catch (error) {
            this.refreshPromise = null;
            console.error(`${this.LOG_PREFIX} Manual refresh failed:`, error);
            return false;
        }
    }

    /** Build the API-shaped TokenData from the current numeric cache. */
    private cachedToTokenData(): TokenData {
        const c = this.cachedTokenData!;
        return {
            access_token: c.access_token,
            token_type: 'bearer',
            expires_at: new Date(c.expires_at).toISOString(),
            refresh_token: c.refresh_token,
            refresh_token_expires_at: c.refresh_token_expires
                ? new Date(c.refresh_token_expires).toISOString()
                : undefined
        };
    }

    /**
     * Run the refresh under a cross-tab exclusive lock (Web Locks API) so only one
     * tab/worker refreshes at a time. This is what keeps the server's single-use
     * refresh-token rotation safe: without it, two tabs whose access token expired
     * would POST /auth/refresh with the SAME refresh token, the server would spend
     * it once and treat the second as a stolen-token replay — revoking the whole
     * session and logging the user out everywhere. Serialized + re-reading the
     * cache first, the loser picks up the winner's freshly-rotated token instead of
     * replaying the spent one. Degrades to a plain call where locks are unavailable.
     */
    private withRefreshLock<T>(fn: () => Promise<T>): Promise<T> {
        const locks = typeof navigator !== 'undefined'
            ? (navigator as Navigator & { locks?: LockManager }).locks
            : undefined;
        if (locks?.request) {
            return locks.request('hillview-auth-refresh', fn) as Promise<T>;
        }
        return fn();
    }

    private async performRefresh(force: boolean = false): Promise<TokenData> {
        return this.withRefreshLock(async () => {
            // Re-read the store now that we hold the lock: another tab may have
            // rotated the tokens while we waited. If so, use theirs and skip the
            // network entirely — a non-force refresh only needs a currently-valid
            // access token and a refresh token that isn't due for renewal.
            await this.refreshCache();
            if (!force
                    && this.cachedTokenData
                    && !(await this.isTokenExpired())
                    && !(await this.shouldRenewRefreshToken())) {
                console.log(`${this.LOG_PREFIX} Another context already refreshed; using stored token`);
                return this.cachedToTokenData();
            }
            return this.performRefreshAttempts(1, 3);
        });
    }

    private async performRefreshAttempts(attempt: number = 1, maxAttempts: number = 3): Promise<TokenData> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.refresh_token) {
            throw new TokenRefreshError('No refresh token available');
        }

        const refreshToken = this.cachedTokenData.refresh_token;
        const refreshExpires = this.cachedTokenData.refresh_token_expires;
        // The access token we're refreshing away from. Used in the 401 branch below
        // to tell a genuinely terminal rejection (cache unchanged) from another tab
        // having refreshed in the meantime (cache now holds a different, valid token).
        const priorAccessToken = this.cachedTokenData.access_token;

        if (!refreshExpires) {
            throw new TokenRefreshError('No refresh token expiry stored');
        }

        // Check if refresh token is expired
        const now = Date.now();
        const bufferTime = 1 * 60 * 1000; // 1 minute buffer

        if (now + bufferTime >= refreshExpires) {
            console.warn(`${this.LOG_PREFIX} Refresh token expired`);
            throw new TokenRefreshError('Refresh token expired');
        }

        const hoursRemaining = Math.round((refreshExpires - now) / (1000 * 60 * 60));
        console.log(`${this.LOG_PREFIX} Refresh token valid (${hoursRemaining} hours remaining)`);

        const refreshStartTime = Date.now();
        console.log(`${this.LOG_PREFIX} Performing token renewal (attempt ${attempt}/${maxAttempts})`);

        // Update auth store with refresh status
        auth.update(state => ({
            ...state,
            refresh_status: attempt === 1 ? 'refreshing' : 'retrying',
            refresh_attempt: attempt
        }));

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 15000);

            const response = await fetch(`${backendUrl}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            const refreshDuration = Date.now() - refreshStartTime;
            console.log(`${this.LOG_PREFIX} Refresh completed in ${refreshDuration}ms, status: ${response.status}`);

            if (!response.ok) {
                const errorText = await response.text();
                let errorDetail;
                try {
                    const errorJson = JSON.parse(errorText);
                    errorDetail = errorJson.detail || errorJson.message || errorText;
                } catch {
                    errorDetail = errorText;
                }
                console.warn(`${this.LOG_PREFIX} Refresh failed: ${response.status} ${errorDetail}`);

                if (response.status === 401 || response.status === 403) {
                    // Optimistic recovery: another tab may have refreshed while we were
                    // in flight. Only accept that if the cache now holds a *different*,
                    // still-valid access token than the one we just failed to refresh.
                    // A force-logout / wiped session leaves our token time-valid but
                    // server-rejected; without the token-changed check, expires_at>now
                    // would mask a genuinely terminal 401 and we'd never log out.
                    await this.refreshCache();
                    if (this.cachedTokenData
                            && this.cachedTokenData.access_token !== priorAccessToken
                            && this.cachedTokenData.expires_at > Date.now()) {
                        console.log(`${this.LOG_PREFIX} Token was refreshed by another context`);
                        return {
                            access_token: this.cachedTokenData.access_token,
                            token_type: 'bearer',
                            expires_at: new Date(this.cachedTokenData.expires_at).toISOString(),
                            refresh_token: this.cachedTokenData.refresh_token,
                            refresh_token_expires_at: this.cachedTokenData.refresh_token_expires
                                ? new Date(this.cachedTokenData.refresh_token_expires).toISOString()
                                : undefined
                        } as TokenData;
                    }
                    throw new TokenRefreshError(`Refresh failed: ${errorDetail}`);
                }
                throw new Error(`HTTP ${response.status}: ${errorDetail}`);
            }

            const tokenData = await response.json() as TokenData;
            await this.storeTokens(tokenData);

            console.log(`${this.LOG_PREFIX} Token refresh successful`);

            auth.update(state => ({
                ...state,
                is_authenticated: true,
                refresh_status: 'idle',
                refresh_attempt: undefined
            }));

            return tokenData;

        } catch (error) {
            const refreshDuration = Date.now() - refreshStartTime;

            if (error instanceof TokenRefreshError) {
                // Terminal: the refresh token was rejected/expired. This is an expected
                // end-of-session outcome (the caller logs out gracefully), not a bug —
                // warn, don't error, so resilience tests' "no error spam" guard holds.
                console.warn(`${this.LOG_PREFIX} Token refresh failed permanently after ${refreshDuration}ms`);
                throw error;
            }

            const isTimeout = error instanceof Error && error.name === 'AbortError';
            const isNetworkError = error instanceof TypeError && error.message.includes('fetch');
            const errorMessage = error instanceof Error ? error.message : String(error);

            console.warn(`${this.LOG_PREFIX} Refresh attempt ${attempt} failed:`,
                isTimeout ? 'timeout' : isNetworkError ? 'network error' : errorMessage);

            if (attempt < maxAttempts && (isTimeout || isNetworkError || errorMessage.includes('HTTP 5'))) {
                const delayMs = Math.pow(2, attempt - 1) * 1000;
                console.log(`${this.LOG_PREFIX} Retrying in ${delayMs}ms...`);
                await new Promise(resolve => setTimeout(resolve, delayMs));
                return this.performRefreshAttempts(attempt + 1, maxAttempts);
            }

            // Transient exhaustion (timeout / network / 5xx, retries spent). The session
            // is kept and a later attempt / reconnect can recover, so this is a warning,
            // not an error — keeps the resilience "no error spam" guard meaningful.
            console.warn(`${this.LOG_PREFIX} Token refresh failed after ${attempt} attempts`);

            auth.update(state => ({
                ...state,
                refresh_status: 'failed',
                refresh_attempt: attempt
            }));

            // Reaching here means the retryable conditions held (timeout / network /
            // 5xx) or attempts were exhausted — a recoverable connectivity failure,
            // not a rejected/expired refresh token. Mark it transient so callers keep
            // the session instead of logging out.
            const transient = isTimeout || isNetworkError || errorMessage.includes('HTTP 5');
            throw new TokenRefreshError(`Refresh failed after ${attempt} attempts: ${errorMessage}`, { transient });
        }
    }

    async storeTokens(tokenData: TokenData): Promise<void> {
        if (tokenData.refresh_token && !tokenData.refresh_token_expires_at) {
            throw new Error('Refresh token provided without expiry date');
        }

        // Convert API format (string dates) to IndexedDB format (number timestamps)
        const indexedDbData: IndexedDbTokenData = {
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token || this.cachedTokenData?.refresh_token || '',
            expires_at: new Date(tokenData.expires_at).getTime(),
            refresh_token_expires: tokenData.refresh_token_expires_at
                ? new Date(tokenData.refresh_token_expires_at).getTime()
                : this.cachedTokenData?.refresh_token_expires
        };

        await authStorage.saveTokenData(indexedDbData);

        // Update local cache
        this.cachedTokenData = indexedDbData;

        console.log(`${this.LOG_PREFIX} Tokens stored in IndexedDB`);

        // NOTE: We intentionally do NOT set is_authenticated here.
        // Auth state is managed by callers (completeAuthentication, performRefresh)
        // so that key registration can complete before triggering photo sync.
    }

    async registerClientPublicKey(): Promise<void> {
        console.log(`${this.LOG_PREFIX} Registering client public key`);

        const keyInfo = await clientCrypto.getPublicKeyInfo();

        const response = await http.post('/auth/register-client-key', {
            public_key_pem: keyInfo.public_key_pem,
            key_id: keyInfo.key_id,
            created_at: keyInfo.created_at
        });

        // 409 = key already registered — treat as success (like Kotlin)
        if (response.ok || response.status === 409) {
            console.log(`${this.LOG_PREFIX} Client public key registered (status: ${response.status})`);
            return;
        }

        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(`Key registration failed: ${error.detail || response.statusText}`);
    }

    async clearTokens(): Promise<void> {
        console.log(`${this.LOG_PREFIX} Clearing tokens`);

        await authStorage.clearTokens();
        this.cachedTokenData = null;

        console.log(`${this.LOG_PREFIX} Tokens cleared from IndexedDB`);

        auth.update(state => ({
            ...state,
            is_authenticated: false,
            user: null
        }));
    }

    async isTokenExpired(bufferMinutes: number = 2): Promise<boolean> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.expires_at) {
            return true;
        }

        const now = Date.now();
        const bufferMs = bufferMinutes * 60 * 1000;
        return (this.cachedTokenData.expires_at - bufferMs) <= now;
    }

    private async shouldRenewRefreshToken(bufferDays: number = 3): Promise<boolean> {
        await this.ensureCacheInitialized();

        if (!this.cachedTokenData?.refresh_token_expires) {
            return false; // No refresh token expiry, can't determine
        }

        const now = Date.now();
        const bufferMs = bufferDays * 24 * 60 * 60 * 1000;
        return now + bufferMs >= this.cachedTokenData.refresh_token_expires;
    }
}
