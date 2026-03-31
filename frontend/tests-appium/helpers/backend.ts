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
