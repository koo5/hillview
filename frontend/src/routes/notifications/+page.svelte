<script lang="ts">
	import { Bell, CheckCheck } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { auth } from '$lib/authStore';
	import { navigateWithHistory } from '$lib/navigation.svelte';
	import { refreshUnreadCount, BADGE_EXCLUDE_TYPE } from '$lib/notifications';

	interface Notification {
		id: number;
		type: string;
		title: string;
		body: string;
		action_data: unknown; // route string (or {route}); tolerated below
		read_at: string | null;
		created_at: string;
	}

	let notifications: Notification[] = [];
	let loading = false;
	let error = '';

	$: authed = $auth.is_authenticated === true;

	let loadedOnce = false;
	$: if (authed && !loadedOnce) {
		loadedOnce = true;
		loadNotifications();
	}

	// The route can arrive as a bare string or {route: ...} in action_data.
	function routeOf(n: Notification): string | null {
		const a = n.action_data as any;
		if (!a) return null;
		if (typeof a === 'string') return a;
		if (typeof a === 'object' && typeof a.route === 'string') return a.route;
		return null;
	}

	async function loadNotifications() {
		loading = true;
		error = '';
		try {
			// Main stream excludes the noisy broadcast; fetch at most one broadcast
			// separately and merge it in, so users see it collapsed to a single row.
			const [mainRes, bcRes] = await Promise.all([
				http.get(`/notifications/recent?exclude_type=${BADGE_EXCLUDE_TYPE}&limit=50`),
				http.get(`/notifications/recent?type=${BADGE_EXCLUDE_TYPE}&limit=1`),
			]);
			if (!mainRes.ok) {
				error = `Failed to load notifications (${mainRes.status})`;
				return;
			}
			const main = (await mainRes.json()).notifications ?? [];
			const bc = bcRes.ok ? ((await bcRes.json()).notifications ?? []) : [];
			notifications = [...main, ...bc].sort(
				(a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
			);
		} catch (e) {
			error = 'Network error loading notifications.';
		} finally {
			loading = false;
		}
	}

	async function markRead(ids: number[]) {
		if (ids.length === 0) return;
		try {
			await http.put('/notifications/read', { notification_ids: ids });
			const set = new Set(ids);
			const now = new Date().toISOString();
			notifications = notifications.map((n) => (set.has(n.id) && !n.read_at ? { ...n, read_at: now } : n));
			await refreshUnreadCount();
		} catch {
			// non-fatal
		}
	}

	$: unreadIds = notifications.filter((n) => !n.read_at).map((n) => n.id);

	async function markAllRead() {
		await markRead(unreadIds);
	}

	async function open(n: Notification) {
		if (!n.read_at) await markRead([n.id]);
		const route = routeOf(n);
		if (route) navigateWithHistory(route);
	}
</script>

<StandardHeaderWithAlert title="Notifications" showMenuButton={true} fallbackHref="/">
	<button
		slot="actions"
		class="mark-all"
		data-testid="notifications-mark-all"
		on:click={markAllRead}
		disabled={unreadIds.length === 0}
		title="Mark all as read"
	>
		<CheckCheck size={18} />
	</button>
</StandardHeaderWithAlert>

<StandardBody>
	<div class="notifications" data-testid="notifications-page">
		<ProfileGate>
			{#if !authed}
				<div class="empty" data-testid="notifications-signed-out">
					<Bell size={24} />
					<p>Log in to see your notifications.</p>
					<a class="link" href="/login">Log in</a>
				</div>
			{:else if loading && notifications.length === 0}
				<div class="empty">Loading…</div>
			{:else if error}
				<div class="error" data-testid="notifications-error">{error}</div>
			{:else if notifications.length === 0}
				<div class="empty" data-testid="notifications-empty">
					<Bell size={24} />
					<p>No notifications yet.</p>
				</div>
			{:else}
				<ul class="list">
					{#each notifications as n (n.id)}
						<li
							class="item"
							class:unread={!n.read_at}
							data-testid="notification-item"
							data-type={n.type}
							data-read={n.read_at ? 'true' : 'false'}
						>
							<button class="item-btn" on:click={() => open(n)}>
								{#if !n.read_at}<span class="dot" aria-label="unread"></span>{/if}
								<span class="item-main">
									<span class="item-title">{n.title}</span>
									<span class="item-body">{n.body}</span>
									<span class="item-time">{formatUtcDateTime(n.created_at)}</span>
								</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

<style>
	.notifications {
		max-width: 720px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.mark-all {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border: none;
		border-radius: 50%;
		background: white;
		color: #374151;
		cursor: pointer;
		box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
	}

	.mark-all:disabled {
		opacity: 0.4;
		cursor: default;
	}

	.empty {
		text-align: center;
		color: #6b7280;
		padding: 48px 16px;
	}

	.empty :global(svg) {
		color: #9ca3af;
		margin-bottom: 8px;
	}

	.link {
		display: inline-block;
		margin-top: 12px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}

	.error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #991b1b;
		padding: 10px 14px;
		border-radius: 8px;
		font-size: 0.875rem;
	}

	.list {
		list-style: none;
		padding: 0;
		margin: 0;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.9);
	}

	.item {
		border-bottom: 1px solid #f3f4f6;
	}

	.item:last-child {
		border-bottom: none;
	}

	.item.unread {
		background: #eff6ff;
	}

	.item-btn {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		padding: 14px 16px;
		cursor: pointer;
		font: inherit;
	}

	.dot {
		flex: 0 0 auto;
		width: 8px;
		height: 8px;
		margin-top: 6px;
		border-radius: 50%;
		background: #2563eb;
	}

	.item-main {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.item-title {
		font-weight: 600;
		color: #1f2937;
	}

	.item-body {
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.item-time {
		font-size: 0.72rem;
		color: #9ca3af;
		margin-top: 2px;
	}
</style>
