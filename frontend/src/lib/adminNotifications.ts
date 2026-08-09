// Admin menu-badge counts. Polls GET /api/admin/notifications while the logged-in
// user is a full admin, and exposes the counts as a store so the hamburger badge,
// the Admin menu item, and the /admin dashboard all read the same numbers.
//
// The counts are derived server-side from durable state (contact messages still at
// status='new', flags still unresolved), so the badge clears itself when items are
// actually handled rather than when they are merely viewed — no per-admin "seen"
// cursor. See backend admin_routes.py.
import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { http } from '$lib/http';
import { auth } from '$lib/authStore';

export interface AdminNotificationCounts {
	contact_new: number;
	flags_open: number;
	total: number;
}

const EMPTY: AdminNotificationCounts = { contact_new: 0, flags_open: 0, total: 0 };

export const adminNotifications = writable<AdminNotificationCounts>(EMPTY);

// The /admin dashboard and its notifications endpoint are admin-only, so gate
// strictly on 'admin'. `role` is surfaced on the profile via /auth/me (UserOut.role).
export const isAdmin = derived(auth, ($auth) => ($auth.user?.role as string | undefined) === 'admin');

// The /moderate surface (a subset of the moderation tools) is open to moderators
// and admins. Admins are implicitly moderators.
export const isModerator = derived(auth, ($auth) => {
	const role = ($auth.user?.role as string | undefined)?.toLowerCase();
	return role === 'admin' || role === 'moderator';
});

const POLL_INTERVAL_MS = 60_000;
let timer: ReturnType<typeof setInterval> | null = null;

export async function refreshAdminNotifications(): Promise<void> {
	if (!browser || !get(isAdmin)) return;
	try {
		const res = await http.get('/admin/notifications');
		if (!res.ok) return; // transient (e.g. 5xx) — keep last known counts
		const data = await res.json();
		adminNotifications.set({
			contact_new: data.contact_new ?? 0,
			flags_open: data.flags_open ?? 0,
			total: data.total ?? 0,
		});
	} catch {
		// network blip — keep last known counts, next tick retries
	}
}

function onWake() {
	void refreshAdminNotifications();
}

function startPolling() {
	if (timer) return;
	void refreshAdminNotifications();
	timer = setInterval(refreshAdminNotifications, POLL_INTERVAL_MS);
	window.addEventListener('focus', onWake);
	document.addEventListener('visibilitychange', onWake);
}

function stopPolling() {
	if (timer) {
		clearInterval(timer);
		timer = null;
		window.removeEventListener('focus', onWake);
		document.removeEventListener('visibilitychange', onWake);
	}
	adminNotifications.set(EMPTY);
}

// Start/stop as admin status changes (login, logout, role, cross-tab login). Both
// helpers are idempotent, so repeated same-value emissions from `auth` are harmless.
if (browser) {
	isAdmin.subscribe((admin) => (admin ? startPolling() : stopPolling()));
}
