<script lang="ts">
	import { onMount } from 'svelte';
	import { Shield, Mail, Flag, ScrollText, MessageSquare, Image, Users, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, adminNotifications, refreshAdminNotifications } from '$lib/adminNotifications';

	interface ActivityEvent {
		kind: 'contact' | 'flag' | 'annotation' | 'moderation' | 'upload' | string;
		id: string;
		at: string;
		since: string;
		actor: string;
		actor_role: string | null;
		event_type: string;
		count: number;
		summary: string;
		link: string | null;
	}

	const KIND_ICON: Record<string, typeof Mail> = {
		contact: Mail,
		flag: Flag,
		annotation: MessageSquare,
		moderation: ScrollText,
		upload: Image,
		user: Users,
	};

	// Highlight actors who aren't staff (admin/moderator) so community activity
	// stands out from staff actions in the feed — same signal as the annotations log.
	function isOrdinary(ev: ActivityEvent): boolean {
		return !['admin', 'moderator'].includes((ev.actor_role ?? '').toLowerCase());
	}

	onMount(refreshAdminNotifications);

	$: counts = $adminNotifications;

	let activity: ActivityEvent[] = [];
	let activityLoading = false;
	let activityError = '';

	// Load the merged feed once the profile confirms admin.
	let activityLoadedOnce = false;
	$: if ($isAdmin && !activityLoadedOnce) {
		activityLoadedOnce = true;
		loadActivity();
	}

	async function loadActivity() {
		activityLoading = true;
		activityError = '';
		try {
			const res = await http.get('/admin/activity?limit=40');
			if (!res.ok) {
				activityError = `Failed to load activity (${res.status})`;
				return;
			}
			const data = await res.json();
			activity = data.events ?? [];
		} catch (e) {
			activityError = 'Network error loading activity.';
		} finally {
			activityLoading = false;
		}
	}
</script>

<StandardHeaderWithAlert title="Admin" showMenuButton={true} fallbackHref="/" />

<StandardBody>
	<div class="admin-dashboard" data-testid="admin-dashboard">
		<ProfileGate>
			{#if $isAdmin}
				<header class="admin-header">
					<div class="admin-icon"><Shield size={28} /></div>
					<div>
						<h1>Admin</h1>
						<p class="admin-tagline">Server activity and moderation at a glance.</p>
					</div>
				</header>

				<section class="card-grid">
					<!-- Live-count cards: numbers come from GET /api/admin/notifications and
					     clear when the underlying items are handled. -->
					<a class="admin-card link" href="/admin/contact" data-testid="admin-card-contact">
						<div class="card-top">
							<Mail size={20} />
							<span class="card-title">Contact messages</span>
						</div>
						<div class="card-count" class:has={counts.contact_new > 0} data-testid="admin-count-contact">
							{counts.contact_new}
						</div>
						<div class="card-sub">new / unhandled</div>
					</a>

					<a class="admin-card link" href="/admin/flags" data-testid="admin-card-flags">
						<div class="card-top">
							<Flag size={20} />
							<span class="card-title">Flagged photos</span>
						</div>
						<div class="card-count" class:has={counts.flags_open > 0} data-testid="admin-count-flags">
							{counts.flags_open}
						</div>
						<div class="card-sub">open / unresolved</div>
					</a>

					<a class="admin-card link" href="/admin/annotations" data-testid="admin-card-annotations">
						<div class="card-top">
							<MessageSquare size={20} />
							<span class="card-title">Annotation activity</span>
						</div>
						<div class="card-sub">creates, edits, deletes — full event log</div>
					</a>

					<a class="admin-card link" href="/admin/audit" data-testid="admin-card-audit">
						<div class="card-top">
							<ScrollText size={20} />
							<span class="card-title">Moderation audit</span>
						</div>
						<div class="card-sub">admin/moderator deletions</div>
					</a>

					<a class="admin-card link" href="/admin/users" data-testid="admin-card-users">
						<div class="card-top">
							<Users size={20} />
							<span class="card-title">User management</span>
						</div>
						<div class="card-sub">roles, suspend, delete</div>
					</a>
				</section>

				<section class="activity" data-testid="admin-activity">
					<h2 class="activity-title">Recent activity</h2>

					{#if activityError}
						<div class="error" data-testid="admin-activity-error">{activityError}</div>
					{/if}

					{#if activityLoading && activity.length === 0}
						<div class="activity-empty">Loading…</div>
					{:else if activity.length === 0}
						<div class="activity-empty" data-testid="admin-activity-empty">No recent activity.</div>
					{:else}
						<ul class="activity-list">
							{#each activity as ev (ev.kind + ev.id)}
								<svelte:element
									this={ev.link ? 'a' : 'div'}
									href={ev.link ?? undefined}
									class="activity-item"
									data-testid="admin-activity-item"
									data-kind={ev.kind}
								>
									<span class="kind kind-{ev.kind}">
										<svelte:component this={KIND_ICON[ev.kind] ?? MessageSquare} size={14} />
									</span>
									<span class="activity-text">
										<span class="actor" class:ordinary={isOrdinary(ev)} data-testid="admin-activity-actor">{ev.actor}</span>
										{ev.summary}
										{#if ev.count > 1}<span class="count">×{ev.count}</span>{/if}
									</span>
									<span class="activity-time">{formatUtcDateTime(ev.at)}</span>
								</svelte:element>
							{/each}
						</ul>
					{/if}
				</section>
			{:else}
				<div class="forbidden" data-testid="admin-forbidden">
					<Lock size={28} />
					<h2>Not authorized</h2>
					<p>This area is for administrators.</p>
					<a class="home-link" href="/">Back to map</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

<style>
	.admin-dashboard {
		max-width: 900px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.admin-header {
		display: flex;
		align-items: center;
		gap: 16px;
		margin: 8px 0 32px 0;
	}

	.admin-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 56px;
		height: 56px;
		flex: 0 0 auto;
		background: linear-gradient(135deg, #e0e7ff, #c7d2fe);
		border-radius: 14px;
		color: #4338ca;
	}

	.admin-header h1 {
		font-size: 2rem;
		font-weight: bold;
		color: #1f2937;
		margin: 0;
	}

	.admin-tagline {
		color: #6b7280;
		margin: 4px 0 0 0;
	}

	.card-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 16px;
	}

	.admin-card {
		background: rgba(255, 255, 255, 0.85);
		border: 1px solid #e5e7eb;
		border-radius: 14px;
		padding: 20px;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
	}

	.admin-card.link {
		display: block;
		text-decoration: none;
		color: inherit;
		transition: box-shadow 0.15s ease, transform 0.15s ease;
	}

	.admin-card.link:hover {
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
		transform: translateY(-1px);
	}

	.card-top {
		display: flex;
		align-items: center;
		gap: 8px;
		color: #4b5563;
	}

	.card-title {
		font-weight: 600;
		font-size: 0.95rem;
	}

	.card-count {
		font-size: 2.25rem;
		font-weight: 700;
		color: #9ca3af;
		margin: 8px 0 2px 0;
		line-height: 1;
	}

	.card-count.has {
		color: #dc2626;
	}

	.card-sub {
		font-size: 0.8rem;
		color: #6b7280;
	}

	.activity {
		margin-top: 40px;
	}

	.activity-title {
		font-size: 1.1rem;
		font-weight: 700;
		color: #1f2937;
		margin: 0 0 12px 0;
	}

	.error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #991b1b;
		padding: 10px 14px;
		border-radius: 8px;
		margin-bottom: 12px;
		font-size: 0.875rem;
	}

	.activity-empty {
		color: #6b7280;
		padding: 24px 4px;
	}

	.activity-list {
		list-style: none;
		padding: 0;
		margin: 0;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.85);
	}

	.activity-item {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 14px;
		border-bottom: 1px solid #f3f4f6;
		text-decoration: none;
		color: #374151;
	}

	.activity-item:last-child {
		border-bottom: none;
	}

	a.activity-item:hover {
		background: #f9fafb;
	}

	.kind {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 26px;
		height: 26px;
		flex: 0 0 auto;
		border-radius: 8px;
		color: #fff;
	}

	.kind-contact {
		background: #4f46e5;
	}
	.kind-flag {
		background: #dc2626;
	}
	.kind-annotation {
		background: #2563eb;
	}
	.kind-moderation {
		background: #b45309;
	}
	.kind-upload {
		background: #059669;
	}
	.kind-user {
		background: #7c3aed;
	}

	.activity-text {
		flex: 1;
		min-width: 0;
		font-size: 0.9rem;
	}

	.activity-text .actor {
		font-weight: 600;
		color: #1f2937;
	}

	/* Non-staff actors get the same amber alert pill as the annotations log. */
	.activity-text .actor.ordinary {
		color: #b45309;
		background: #fef3c7;
		padding: 1px 8px;
		border-radius: 999px;
	}

	.count {
		font-size: 0.75rem;
		font-weight: 700;
		color: #6b7280;
		background: #f3f4f6;
		padding: 1px 6px;
		border-radius: 999px;
		margin-left: 2px;
	}

	.activity-time {
		flex: 0 0 auto;
		font-size: 0.72rem;
		color: #9ca3af;
		white-space: nowrap;
	}

	.forbidden {
		text-align: center;
		padding: 64px 24px;
		color: #4b5563;
	}

	.forbidden :global(svg) {
		color: #9ca3af;
		margin-bottom: 12px;
	}

	.forbidden h2 {
		margin: 0 0 8px 0;
		color: #1f2937;
	}

	.home-link {
		display: inline-block;
		margin-top: 16px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}

	.home-link:hover {
		text-decoration: underline;
	}
</style>
