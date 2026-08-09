// Personal notification unread count for the nav bell badge. Polls
// GET /api/notifications/unread-count while logged in. 'activity_broadcast' is
// excluded entirely for now — it's high-volume and untargeted; a future
// follow-based targeted broadcast could count differently.
import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { http } from '$lib/http';
import { auth } from '$lib/authStore';

// Types whose unread rows should not drive the badge.
export const BADGE_EXCLUDE_TYPE = 'activity_broadcast';

export const unreadCount = writable<number>(0);

export const isAuthed = derived(auth, ($auth) => $auth.is_authenticated === true);

const POLL_INTERVAL_MS = 60_000;
let timer: ReturnType<typeof setInterval> | null = null;

export async function refreshUnreadCount(): Promise<void> {
	if (!browser || !get(isAuthed)) return;
	try {
		const res = await http.get(`/notifications/unread-count?exclude_type=${BADGE_EXCLUDE_TYPE}`);
		if (!res.ok) return;
		const data = await res.json();
		unreadCount.set(data.unread_count ?? 0);
	} catch {
		// transient — keep last known count
	}
}

function onWake() {
	void refreshUnreadCount();
}

function startPolling() {
	if (timer) return;
	void refreshUnreadCount();
	timer = setInterval(refreshUnreadCount, POLL_INTERVAL_MS);
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
	unreadCount.set(0);
}

if (browser) {
	isAuthed.subscribe((authed) => (authed ? startPolling() : stopPolling()));
}
