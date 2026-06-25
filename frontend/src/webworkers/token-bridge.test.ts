import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getValidToken, handleMessage, reset } from './new.worker';

// A postMessage spy that does NOT auto-respond, so the test controls when (and in
// which order) the main thread "replies" with authToken messages.
const postSpy = vi.fn();

beforeEach(() => {
    reset({ postMessage: postSpy });
    postSpy.mockClear();
});

function respond(requestId: number, token: string | null): void {
    handleMessage({ type: 'authToken', requestId, token });
}
function postedRequestId(callIndex: number): number {
    return postSpy.mock.calls[callIndex][0].requestId;
}

describe('worker token bridge — request/response correlation', () => {
    it('routes out-of-order responses to the right request (no crossing)', async () => {
        const p1 = getValidToken();
        const p2 = getValidToken();

        expect(postSpy).toHaveBeenCalledTimes(2);
        const id1 = postedRequestId(0);
        const id2 = postedRequestId(1);
        expect(id1).not.toBe(id2);

        // Reply in reverse order — the old single-resolver bridge would cross these.
        respond(id2, 'token-2');
        respond(id1, 'token-1');

        await expect(p1).resolves.toBe('token-1');
        await expect(p2).resolves.toBe('token-2');
    });

    it('ignores a response with an unknown / already-settled request id', async () => {
        const p1 = getValidToken();
        const id1 = postedRequestId(0);

        respond(id1, 'token-1');
        await expect(p1).resolves.toBe('token-1');

        // A duplicate / late reply for the same id must be a harmless no-op.
        expect(() => respond(id1, 'stale')).not.toThrow();
        expect(() => respond(9999, 'never-requested')).not.toThrow();
    });

    it('times out an unanswered request and cleans it up', async () => {
        vi.useFakeTimers();
        try {
            const p = getValidToken();
            await vi.advanceTimersByTimeAsync(25_000); // past TOKEN_REQUEST_TIMEOUT_MS (20s)

            await expect(p).resolves.toBeNull();

            // A reply arriving after the timeout finds no pending entry → ignored.
            const id = postedRequestId(0);
            expect(() => respond(id, 'too-late')).not.toThrow();
        } finally {
            vi.useRealTimers();
        }
    });

    it('reset() resolves any in-flight token requests with null', async () => {
        const p = getValidToken();

        reset({ postMessage: postSpy }); // re-init drains the pending map

        await expect(p).resolves.toBeNull();
    });
});
