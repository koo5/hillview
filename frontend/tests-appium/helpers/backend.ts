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

    return {
        passwords,
        users_created: result.details?.created_users || [],
        users_deleted: result.details?.users_deleted || 0,
    };
}
