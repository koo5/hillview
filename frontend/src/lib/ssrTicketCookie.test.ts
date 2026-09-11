/**
 * The cookie is the whole interface between the browser's session and the
 * server's view of it, and it is written from three places (login, refresh, and
 * the broadcast handler that covers other tabs and the service worker). Nothing
 * downstream fails loudly when it is wrong: the server just renders anonymously,
 * which looks exactly like the behaviour this feature replaced.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { setSsrTicketCookie, clearSsrTicketCookie, SSR_TICKET_COOKIE } from './ssrTicketCookie';

const HOUR_AWAY = () => new Date(Date.now() + 3600_000).toISOString();

/**
 * The ticket the server would receive, or null for none.
 *
 * An empty value counts as none: engines differ on whether clearing removes the
 * cookie or blanks it (happy-dom blanks), and either way the server's
 * `cookies.get()` yields a falsy string and renders anonymously.
 */
function readTicket(): string | null {
	const match = new RegExp(`(?:^|;\\s*)${SSR_TICKET_COOKIE}=([^;]*)`).exec(document.cookie);
	const value = match ? decodeURIComponent(match[1]) : '';
	return value || null;
}

describe('ssr ticket cookie', () => {
	beforeEach(() => {
		clearSsrTicketCookie();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('stores the ticket so the server receives it', () => {
		setSsrTicketCookie('ticket-abc', HOUR_AWAY());
		expect(readTicket()).toBe('ticket-abc');
	});

	it('replaces an older ticket rather than accumulating', () => {
		setSsrTicketCookie('first', HOUR_AWAY());
		setSsrTicketCookie('second', HOUR_AWAY());
		expect(readTicket()).toBe('second');
		// Every refresh mints a new ticket; two cookies of the same name would leave
		// the server reading whichever the browser sent first.
		const occurrences = document.cookie.split(';').filter((c) => c.trim().startsWith(`${SSR_TICKET_COOKIE}=`));
		expect(occurrences).toHaveLength(1);
	});

	it('clears on logout', () => {
		setSsrTicketCookie('ticket-abc', HOUR_AWAY());
		clearSsrTicketCookie();
		expect(readTicket()).toBeNull();
	});

	it('treats an already-expired ticket as no ticket', () => {
		setSsrTicketCookie('stale', new Date(Date.now() - 1000).toISOString());
		// Pinning a cookie the server would only reject buys nothing, and it would
		// keep the page marked as authed-rendered while the render is anonymous.
		expect(readTicket()).toBeNull();
	});

	it('treats a ticket with no usable expiry as no ticket', () => {
		setSsrTicketCookie('ticket-abc', undefined);
		expect(readTicket()).toBeNull();
		setSsrTicketCookie('ticket-abc', 'not a date');
		expect(readTicket()).toBeNull();
	});

	it('drops the cookie when handed no ticket at all', () => {
		setSsrTicketCookie('ticket-abc', HOUR_AWAY());
		setSsrTicketCookie(undefined, HOUR_AWAY());
		// The mirror is called with whatever storage holds, so "no ticket" arrives
		// this way on logout in another tab.
		expect(readTicket()).toBeNull();
	});

	it('says so when the browser refuses to store it', () => {
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		// A browser with cookies blocked ignores the assignment silently — no throw,
		// nothing stored — and the only symptom would be a signed-in visitor
		// mysteriously getting the anonymous first paint.
		const original = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
		Object.defineProperty(document, 'cookie', { get: () => '', set: () => {}, configurable: true });

		setSsrTicketCookie('ticket-abc', HOUR_AWAY());

		if (original) Object.defineProperty(document, 'cookie', original);
		expect(warn).toHaveBeenCalled();
	});
});
