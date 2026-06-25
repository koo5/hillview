/**
 * Backend API helpers for test setup/teardown.
 * Backend URL as seen from the test runner (not from the emulator).
 */

const BACKEND_URL = 'http://localhost:8055';

export interface TestUserSetupResult {
    passwords: { test: string; admin: string; testuser: string };
    users_created: string[];
    users_deleted: number;
}

/** Cached result from recreateTestUsers() for use in loginAsTestUser(). */
let _lastSetup: TestUserSetupResult | null = null;

/**
 * Recreate test users with clean state.
 * This cascade-deletes photos, hidden_users, annotations etc.
 */
export async function recreateTestUsers(): Promise<TestUserSetupResult> {
    const res = await fetch(`${BACKEND_URL}/api/debug/recreate-test-users`, { method: 'POST' });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`recreate-test-users failed (${res.status}): ${body}`);
    }

    const result = await res.json();
    if (result.detail) {
        throw new Error(`recreate-test-users API error: ${result.detail}`);
    }

    const passwords = result.details?.user_passwords;
    if (!passwords?.test) {
        throw new Error(`Test user password not in response: ${JSON.stringify(result)}`);
    }

    _lastSetup = {
        passwords,
        users_created: result.details?.created_users || [],
        users_deleted: result.details?.users_deleted || 0,
    };
    return _lastSetup;
}

/**
 * Login as test user via the WebView login form.
 * Requires recreateTestUsers() to have been called first.
 */
export async function loginAsTestUser(): Promise<void> {
    if (!_lastSetup) {
        throw new Error('Call recreateTestUsers() before loginAsTestUser()');
    }

    const { ensureWebViewContext, byTestId, TESTID } = await import('./selectors');

    // Open menu and navigate to login
    const menuBtn = await byTestId(TESTID.hamburgerMenu);
    await menuBtn.click();
    await driver.pause(1000);

    await ensureWebViewContext();
    const loginLink = await $('a[href="/login"]');
    await loginLink.waitForDisplayed({ timeout: 5000 });
    await loginLink.click();
    await driver.pause(2000);

    // Fill login form
    await ensureWebViewContext();
    const usernameInput = await $('input#username');
    await usernameInput.waitForDisplayed({ timeout: 5000 });
    await usernameInput.setValue('test');

    const passwordInput = await $('input#password');
    await passwordInput.setValue(_lastSetup.passwords.test);

    const submitBtn = await $('button[type="submit"]');
    await submitBtn.click();
    await driver.pause(3000);
}

/**
 * Logout via the navigation menu.
 */
export async function logout(): Promise<void> {
    const { byTestId, ensureWebViewContext, TESTID } = await import('./selectors');

    const menuBtn = await byTestId(TESTID.hamburgerMenu);
    await menuBtn.click();
    await driver.pause(1000);

    await ensureWebViewContext();
    const logoutBtn = await $('button*=Logout');
    await logoutBtn.waitForDisplayed({ timeout: 5000 });
    await logoutBtn.click();
    await driver.pause(2000);
}

/**
 * Login to the backend API directly and return a JWT token.
 * Useful for making authenticated API calls from the test runner.
 */
export async function getTestUserToken(): Promise<string> {
    if (!_lastSetup) {
        throw new Error('Call recreateTestUsers() before getTestUserToken()');
    }

    const res = await fetch(`${BACKEND_URL}/api/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
            username: 'test',
            password: _lastSetup.passwords.test,
        }),
    });

    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Login failed (${res.status}): ${body}`);
    }

    const data = await res.json();
    return data.access_token;
}

/**
 * Blacklist a JWT token by calling the backend logout endpoint.
 * Useful for testing token invalidation scenarios.
 */
export async function blacklistToken(token: string): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`blacklistToken failed (${res.status}): ${body}`);
    }
}

/**
 * Set (or clear) an artificial delay on a named backend hot-path via
 * the internal-only knobs endpoint. Seconds=0 clears. The endpoint is
 * localhost-guarded (`require_internal_ip`) and safe to ship — useful
 * in dev for tests that need a wider observation window, and in prod
 * for reproducing slow-network behavior on demand.
 *
 * Current knobs:
 *   - "authorize_upload": sleeps just before returning the JWT in
 *     POST /api/photos/authorize-upload (each queued upload hits this
 *     once, so N seconds here stretches the worker's total runtime by
 *     N × photo-count).
 */
export async function setBackendDelay(name: string, seconds: number): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/delays`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, seconds }),
    });
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`setBackendDelay(${name}=${seconds}) failed (${res.status}): ${body}`);
    }
}

/**
 * Query the backend API for user photos.
 * Returns the count and list of photo IDs.
 */
export async function getUserPhotos(token: string): Promise<{ count: number; ids: string[] }> {
    const res = await fetch(`${BACKEND_URL}/api/photos/`, {
        headers: { Authorization: `Bearer ${token}` },
    });

    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Get photos failed (${res.status}): ${body}`);
    }

    const data = await res.json();
    const photos = Array.isArray(data) ? data : data.photos || [];
    return {
        count: photos.length,
        ids: photos.map((p: any) => p.id || p.photo_id),
    };
}

// -------------------- internal debug hooks (localhost-only) --------------------

async function postDebug(path: string, body: unknown): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        throw new Error(`debug/${path} failed (${res.status}): ${await res.text()}`);
    }
}

/** Mark a user force-logged-out (access + refresh now 401), or clear the flag. */
export async function forceLogoutUser(username: string, clear = false): Promise<void> {
    await postDebug('force-logout-user', { username, clear });
}

/** Override a user's access-token TTL (applied at next login), or clear it. */
export async function setAccessTtl(username: string, seconds: number, clear = false): Promise<void> {
    await postDebug('set-access-ttl', { username, seconds, clear });
}

/** Inject artificial latency into a named backend hot-path (0 to clear). */
export async function setDebugDelay(name: string, seconds: number): Promise<void> {
    await postDebug('delays', { name, seconds });
}

/**
 * Arm a chaos-monkey HTTP fault on the api: requests whose path matches `path`
 * (a glob, e.g. '/api/auth/me' or '/api/auth/*') fail with `status`, for `count`
 * requests (or until cleared), optionally after `delaySeconds`.
 */
export async function armFault(
    path: string,
    opts: { status?: number; count?: number; delaySeconds?: number; methods?: string[]; detail?: string } = {},
): Promise<void> {
    await postDebug('faults', {
        path,
        status: opts.status,
        count: opts.count,
        delay_seconds: opts.delaySeconds,
        methods: opts.methods,
        detail: opts.detail,
    });
}

/** Clear all armed HTTP faults on the api. */
export async function clearFaults(): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/faults`, { method: 'DELETE' });
    if (!res.ok) {
        throw new Error(`clear faults failed (${res.status}): ${await res.text()}`);
    }
}

// Worker service URL as seen from the test runner (WORKER_URL default in compose).
const WORKER_URL = 'http://localhost:8056';

async function postWorkerFaults(body: unknown): Promise<void> {
    const res = await fetch(`${WORKER_URL}/debug/faults`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        throw new Error(`worker /debug/faults failed (${res.status}): ${await res.text()}`);
    }
}

/** Arm a chaos-monkey fault on the WORKER (e.g. the photo-upload endpoint). */
export async function armWorkerFault(
    path: string,
    opts: { status?: number; count?: number; delaySeconds?: number; methods?: string[] } = {},
): Promise<void> {
    await postWorkerFaults({
        path,
        status: opts.status,
        count: opts.count,
        delay_seconds: opts.delaySeconds,
        methods: opts.methods,
    });
}

/** Clear all armed faults on the worker. */
export async function clearWorkerFaults(): Promise<void> {
    const res = await fetch(`${WORKER_URL}/debug/faults`, { method: 'DELETE' });
    if (!res.ok) {
        throw new Error(`clear worker faults failed (${res.status}): ${await res.text()}`);
    }
}
