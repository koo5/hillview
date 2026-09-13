import { describe, it, expect, vi } from 'vitest';
import { createSsrBackedLoad } from './ssrBackedLoad';

const ALICE = 'user-alice';
const BOB = 'user-bob';

const UNCHECKED = { checked: false, is_authenticated: false, userId: null };
const ANON = { checked: true, is_authenticated: false, userId: null };
const ALICE_SIGNED_IN = { checked: true, is_authenticated: true, userId: ALICE };
const BOB_SIGNED_IN = { checked: true, is_authenticated: true, userId: BOB };

// What the server rendered the batch for: a user id, null for the anonymous
// view, or false for "no server batch at all" (Tauri, dev build).
const ANON_BATCH = null;
const NO_BATCH = false;

describe('createSsrBackedLoad', () => {
	it('never fetches for an anonymous visitor who already has the anonymous batch', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ANON_BATCH, load);
		sync(UNCHECKED);
		sync(ANON);
		sync(ANON);
		// The regression this guards: refetching here replaced the server-rendered
		// grid with an error page for crawlers (robots.txt blocks /api/) → soft 404
		expect(load).not.toHaveBeenCalled();
	});

	it('fetches for an anonymous visitor with no SSR batch (Tauri / dev build)', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(NO_BATCH, load);
		sync(ANON);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('fetches for a signed-in visitor when the batch is the anonymous one', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ANON_BATCH, load);
		sync(ALICE_SIGNED_IN);
		sync(ALICE_SIGNED_IN);
		// Every signed-in visit looked like this before the server had a ticket: the
		// batch lacks their hidden-content filtering.
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('does not fetch when the server already rendered this visitor’s own view', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ALICE, load);
		sync(UNCHECKED);
		sync(ALICE_SIGNED_IN);
		sync(ALICE_SIGNED_IN);
		// The whole point of the SSR ticket.
		expect(load).not.toHaveBeenCalled();
	});

	it('fetches when the batch was rendered for somebody else', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ALICE, load);
		// Rare but real: a document restored from back/forward cache after signing in
		// as another account. A boolean "was this authed" cannot see this case.
		sync(BOB_SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('fetches when an anonymous visitor lands on a signed-in batch', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ALICE, load);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('waits for auth to settle before deciding', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(NO_BATCH, load);
		sync(UNCHECKED);
		expect(load).not.toHaveBeenCalled();
		// is_authenticated reads false until hydration lands; acting on the unchecked
		// state would fetch the anonymous view for a signed-in visitor
		sync(ALICE_SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('reloads when the visitor logs in, and again when they log out', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(ANON_BATCH, load);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(0);
		sync(ALICE_SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(2);
	});
});
