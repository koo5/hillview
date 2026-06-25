/**
 * Chaos-monkey / fault-injection helpers for resilience tests.
 *
 * Drive the backend's internal debug hooks (localhost-only, gated on
 * DEBUG_ENDPOINTS) to make individual endpoints fail, slow, expire tokens, or
 * reject a user — then assert the web app recuperates.
 */
import { BACKEND_URL } from './adminAuth';

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

export interface FaultOpts {
    status?: number;
    count?: number;
    delaySeconds?: number;
    methods?: string[];
    detail?: string;
}

/** Arm an HTTP fault: requests whose path matches `path` (a glob) fail with `status`. */
export async function armFault(path: string, opts: FaultOpts = {}): Promise<void> {
    await postDebug('faults', {
        path,
        status: opts.status,
        count: opts.count,
        delay_seconds: opts.delaySeconds,
        methods: opts.methods,
        detail: opts.detail,
    });
}

/** Clear all armed HTTP faults. */
export async function clearFaults(): Promise<void> {
    const res = await fetch(`${BACKEND_URL}/api/internal/debug/faults`, { method: 'DELETE' });
    if (!res.ok) {
        throw new Error(`clear faults failed (${res.status}): ${await res.text()}`);
    }
}

/** Mark a user force-logged-out server-side (access + refresh now 401), or clear it. */
export async function forceLogoutUser(username: string, clear = false): Promise<void> {
    await postDebug('force-logout-user', { username, clear });
}

/** Override a user's access-token TTL (applied at next login), or clear it. */
export async function setAccessTtl(username: string, seconds: number, clear = false): Promise<void> {
    await postDebug('set-access-ttl', { username, seconds, clear });
}
