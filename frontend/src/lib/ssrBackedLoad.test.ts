import { describe, it, expect, vi } from 'vitest';
import { createSsrBackedLoad } from './ssrBackedLoad';

const UNCHECKED = { checked: false, is_authenticated: false };
const ANON = { checked: true, is_authenticated: false };
const SIGNED_IN = { checked: true, is_authenticated: true };

describe('createSsrBackedLoad', () => {
	it('never fetches for an anonymous visitor who already has the SSR batch', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(true, load);
		sync(UNCHECKED);
		sync(ANON);
		sync(ANON);
		// The regression this guards: refetching here replaced the server-rendered
		// grid with an error page for crawlers (robots.txt blocks /api/) → soft 404
		expect(load).not.toHaveBeenCalled();
	});

	it('fetches for an anonymous visitor with no SSR batch (Tauri / dev build)', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(false, load);
		sync(ANON);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('fetches for a signed-in visitor even when SSR provided a batch', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(true, load);
		sync(SIGNED_IN);
		sync(SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('waits for auth to settle before deciding', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(false, load);
		sync(UNCHECKED);
		expect(load).not.toHaveBeenCalled();
		// is_authenticated reads false until hydration lands; acting on the
		// unchecked state would fetch the anonymous view for a signed-in visitor
		sync(SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
	});

	it('reloads when the visitor logs in, and again when they log out', () => {
		const load = vi.fn();
		const sync = createSsrBackedLoad(true, load);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(0);
		sync(SIGNED_IN);
		expect(load).toHaveBeenCalledTimes(1);
		sync(ANON);
		expect(load).toHaveBeenCalledTimes(2);
	});
});
