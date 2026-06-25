import { describe, it, expect, vi } from 'vitest';

// Keep the module's singleton-construction guards inert; we test the class directly.
vi.mock('$lib/tauri', () => ({ TAURI: false }));
vi.mock('$app/environment', () => ({ browser: false }));

import { KotlinMessageQueue, type QueuedMessage } from '$lib/KotlinMessageQueue';

function msg(type: string): QueuedMessage {
    return { type, payload: { v: type }, timestamp: 0 };
}

// handleMessage is private (normally driven by pollMessages); call it directly to
// simulate a message being polled, without timers/invoke.
function deliver(q: KotlinMessageQueue, type: string): void {
    (q as unknown as { handleMessage(m: QueuedMessage): void }).handleMessage(msg(type));
}

describe('KotlinMessageQueue', () => {
    it('dispatches a message to a registered handler', () => {
        const q = new KotlinMessageQueue();
        const handler = vi.fn();
        q.on('foo', handler);

        deliver(q, 'foo');

        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler).toHaveBeenCalledWith(expect.objectContaining({ type: 'foo' }));
    });

    it('drops a NON-critical message that arrives before any handler', () => {
        const q = new KotlinMessageQueue();
        const handler = vi.fn();

        deliver(q, 'some-event'); // no handler yet → dropped
        q.on('some-event', handler);

        expect(handler).not.toHaveBeenCalled();
    });

    it('buffers a CRITICAL message with no handler and re-delivers on registration', () => {
        const q = new KotlinMessageQueue();
        const handler = vi.fn();

        deliver(q, 'auth-expired'); // arrives before the handler exists
        expect(handler).not.toHaveBeenCalled();

        q.on('auth-expired', handler); // handler registers later

        expect(handler).toHaveBeenCalledTimes(1);
        expect(handler).toHaveBeenCalledWith(expect.objectContaining({ type: 'auth-expired' }));
    });

    it('delivers a critical message directly when a handler is already registered', () => {
        const q = new KotlinMessageQueue();
        const handler = vi.fn();
        q.on('auth-expired', handler);

        deliver(q, 'auth-expired');

        expect(handler).toHaveBeenCalledTimes(1);
    });

    it('does not re-deliver an already-flushed buffered message to a later handler', () => {
        const q = new KotlinMessageQueue();
        const first = vi.fn();
        const second = vi.fn();

        deliver(q, 'auth-expired');
        q.on('auth-expired', first); // flushes the buffered message
        q.on('auth-expired', second); // buffer already drained

        expect(first).toHaveBeenCalledTimes(1);
        expect(second).not.toHaveBeenCalled();
    });

    it('buffers multiple critical messages and delivers them in order', () => {
        const q = new KotlinMessageQueue();
        const handler = vi.fn();

        deliver(q, 'auth-expired');
        deliver(q, 'auth-expired');
        q.on('auth-expired', handler);

        expect(handler).toHaveBeenCalledTimes(2);
    });

    it('logs (rather than leaks as an unhandled rejection) when an async handler rejects', async () => {
        const q = new KotlinMessageQueue();
        const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const handler = vi.fn(async () => { throw new Error('boom'); });
        q.on('auth-expired', handler);

        deliver(q, 'auth-expired');
        await new Promise((resolve) => setTimeout(resolve, 0)); // let the .catch microtask run

        expect(handler).toHaveBeenCalledTimes(1);
        expect(errorSpy).toHaveBeenCalledWith(
            expect.stringContaining('Error in async handler'),
            expect.any(Error),
        );
        errorSpy.mockRestore();
    });
});
