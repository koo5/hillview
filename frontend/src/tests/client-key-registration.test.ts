import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// The module under test talks to the token manager (registration request) and
// to connectivity (reconnect re-kick); both are replaced so the run can be driven.
const registerMock = vi.hoisted(() => vi.fn<() => Promise<void>>());
const managerRef = vi.hoisted(() => ({ current: {} as Record<string, unknown> }));
const reconnectHandlers = vi.hoisted(() => [] as Array<() => void>);

vi.mock('$lib/tokenManagerFactory', () => ({
    createTokenManager: () => managerRef.current,
}));
vi.mock('$lib/connectivity', () => ({
    onReconnect: (handler: () => void) => {
        reconnectHandlers.push(handler);
        return () => {};
    },
}));

import {
    ensureClientKeyRegistered,
    startClientKeyRegistration,
    resetClientKeyRegistration,
    RETRY_DELAYS_MS,
    _resetForTests,
} from '$lib/clientKeyRegistration';
import { ClientKeyRegistrationError } from '$lib/tokenManager';

function tokenExpired(): Error {
    return Object.assign(new Error('Token expired and refresh failed'), { name: 'TokenExpiredError' });
}

/** Resolve the microtask queue without advancing timers. */
async function flush(): Promise<void> {
    await vi.advanceTimersByTimeAsync(0);
}

beforeEach(() => {
    // Only the timers the run uses. vitest 4's default fake set makes every
    // hook in this file hang (10 s hook timeout); the explicit list does not.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval', 'Date'] });
    registerMock.mockReset();
    managerRef.current = { registerClientPublicKey: registerMock };
    _resetForTests();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe('ensureClientKeyRegistered', () => {
    it('registers once and shares the run between concurrent callers', async () => {
        registerMock.mockResolvedValue(undefined);

        await Promise.all([ensureClientKeyRegistered(), ensureClientKeyRegistered()]);
        await ensureClientKeyRegistered();

        expect(registerMock).toHaveBeenCalledTimes(1);
    });

    it('retries a network failure on the schedule and then resolves', async () => {
        registerMock.mockRejectedValueOnce(new Error('fetch failed')).mockResolvedValue(undefined);

        const done = ensureClientKeyRegistered();
        await flush();
        expect(registerMock).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0] - 1);
        expect(registerMock).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(1);
        await expect(done).resolves.toBeUndefined();
        expect(registerMock).toHaveBeenCalledTimes(2);
    });

    it('retries a 5xx from the server', async () => {
        registerMock
            .mockRejectedValueOnce(new ClientKeyRegistrationError(503, 'unavailable'))
            .mockResolvedValue(undefined);

        const done = ensureClientKeyRegistered();
        await vi.advanceTimersByTimeAsync(RETRY_DELAYS_MS[0]);

        await expect(done).resolves.toBeUndefined();
        expect(registerMock).toHaveBeenCalledTimes(2);
    });

    it('does not retry a 4xx: the request itself is wrong', async () => {
        registerMock.mockRejectedValue(new ClientKeyRegistrationError(422, 'bad key'));

        const done = ensureClientKeyRegistered();
        await expect(done).rejects.toBeInstanceOf(ClientKeyRegistrationError);
        await vi.advanceTimersByTimeAsync(60_000);

        expect(registerMock).toHaveBeenCalledTimes(1);
    });

    it('stops when the session has ended', async () => {
        registerMock.mockRejectedValue(tokenExpired());

        await expect(ensureClientKeyRegistered()).rejects.toMatchObject({ name: 'TokenExpiredError' });
        await vi.advanceTimersByTimeAsync(60_000);

        expect(registerMock).toHaveBeenCalledTimes(1);
    });

    it('gives up after the schedule and lets the next caller start a fresh run', async () => {
        registerMock.mockRejectedValue(new Error('fetch failed'));

        const done = ensureClientKeyRegistered();
        done.catch(() => {});
        for (const delay of RETRY_DELAYS_MS) {
            await vi.advanceTimersByTimeAsync(delay);
        }
        await expect(done).rejects.toThrow('fetch failed');
        expect(registerMock).toHaveBeenCalledTimes(RETRY_DELAYS_MS.length + 1);

        registerMock.mockResolvedValue(undefined);
        await expect(ensureClientKeyRegistered()).resolves.toBeUndefined();
        expect(registerMock).toHaveBeenCalledTimes(RETRY_DELAYS_MS.length + 2);
    });

    it('discards a run that outlives its session', async () => {
        let finish!: () => void;
        registerMock.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));

        const stale = ensureClientKeyRegistered();
        stale.catch(() => {});
        await flush();
        resetClientKeyRegistration();
        finish();

        await expect(stale).rejects.toMatchObject({ name: 'SessionChangedError' });

        // The new session has to register for itself.
        registerMock.mockResolvedValue(undefined);
        await ensureClientKeyRegistered();
        expect(registerMock).toHaveBeenCalledTimes(2);
    });

    it('is a no-op on a token manager without registration (Android owns the key)', async () => {
        managerRef.current = {};

        await expect(ensureClientKeyRegistered()).resolves.toBeUndefined();
        expect(registerMock).not.toHaveBeenCalled();
    });
});

describe('startClientKeyRegistration', () => {
    it('never rejects, so a login cannot fail over it', async () => {
        registerMock.mockRejectedValue(new ClientKeyRegistrationError(400, 'rejected'));

        expect(() => startClientKeyRegistration()).not.toThrow();
        await flush();

        expect(registerMock).toHaveBeenCalledTimes(1);
        expect(console.error).toHaveBeenCalled();
    });
});

describe('reconnect', () => {
    it('re-kicks a run that gave up, for a session that still wants the key', async () => {
        registerMock.mockRejectedValue(new Error('fetch failed'));
        const done = ensureClientKeyRegistered();
        done.catch(() => {});
        for (const delay of RETRY_DELAYS_MS) {
            await vi.advanceTimersByTimeAsync(delay);
        }
        await expect(done).rejects.toThrow();
        const attempts = registerMock.mock.calls.length;

        registerMock.mockResolvedValue(undefined);
        for (const handler of reconnectHandlers) handler();
        await flush();

        expect(registerMock).toHaveBeenCalledTimes(attempts + 1);
        await expect(ensureClientKeyRegistered()).resolves.toBeUndefined();
        expect(registerMock).toHaveBeenCalledTimes(attempts + 1);
    });

    it('does nothing when no session asked for the key', async () => {
        registerMock.mockResolvedValue(undefined);

        for (const handler of reconnectHandlers) handler();
        await flush();

        expect(registerMock).not.toHaveBeenCalled();
    });
});
