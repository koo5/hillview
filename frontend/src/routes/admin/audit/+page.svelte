<script lang="ts">
	import { ScrollText, Trash2, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, isModerator } from '$lib/adminNotifications';

	interface AuditEntry {
		id: string;
		action: string;
		actor_user_id: string;
		actor_username: string | null;
		actor_role: string | null;
		photo_source: string;
		photo_id: string;
		photo_owner_id: string | null;
		photo_owner_username: string | null;
		reason: string | null;
		extra_data: Record<string, unknown> | null;
		created_at: string;
	}

	let entries: AuditEntry[] = [];
	let loading = false;
	let error = '';

	let loadedOnce = false;
	$: if ($isModerator && !loadedOnce) {
		loadedOnce = true;
		loadEntries();
	}

	async function loadEntries() {
		loading = true;
		error = '';
		try {
			const res = await http.get('/photos/moderation-audit?limit=100');
			if (!res.ok) {
				error = `Failed to load audit (${res.status})`;
				return;
			}
			const data = await res.json();
			entries = data.entries ?? [];
		} catch (e) {
			error = 'Network error loading audit.';
		} finally {
			loading = false;
		}
	}

	// The snapshotted photo filename/title, if the audit row captured one.
	function photoLabel(ev: AuditEntry): string {
		const x = ev.extra_data ?? {};
		const title = (x.title as string) || '';
		const filename = (x.original_filename as string) || (x.filename as string) || '';
		return title || filename || '';
	}
</script>

<StandardHeaderWithAlert title="Moderation audit" showMenuButton={true} fallbackHref={$isAdmin ? '/admin' : '/moderate'} />

<StandardBody>
	<div class="admin-audit" data-testid="admin-audit-page">
		<ProfileGate>
			{#if $isModerator}
				<p class="intro">
					Moderator/admin actions on photos they don't own, newest first. Records
					survive deletion of the actor, owner, or photo.
				</p>

				{#if error}
					<div class="error" data-testid="admin-audit-error">{error}</div>
				{/if}

				{#if loading && entries.length === 0}
					<div class="empty">Loading…</div>
				{:else if entries.length === 0}
					<div class="empty" data-testid="admin-audit-empty">
						<ScrollText size={24} />
						<p>No moderation actions recorded.</p>
					</div>
				{:else}
					<ul class="entry-list">
						{#each entries as ev (ev.id)}
							<li class="entry" data-testid="admin-audit-entry" data-entry-id={ev.id} data-action={ev.action}>
								<span class="action action-{ev.action}">
									<Trash2 size={13} /> {ev.action}
								</span>
								<div class="entry-main">
									<div class="line">
										<span class="actor" data-testid="admin-audit-actor">{ev.actor_username ?? ev.actor_user_id}</span>
										{#if ev.actor_role}<span class="role">{ev.actor_role}</span>{/if}
										<span class="verb">removed</span>
										<span class="owner" data-testid="admin-audit-owner">{ev.photo_owner_username ?? 'unknown'}</span><span class="verb">'s photo</span>
									</div>
									<div class="meta">
										<span class="photo" title={`photo ${ev.photo_id}`}>{ev.photo_source} · {ev.photo_id.slice(0, 12)}…</span>
										{#if photoLabel(ev)}
											<span class="dot">·</span><span class="filename">{photoLabel(ev)}</span>
										{/if}
										<span class="dot">·</span>
										<span>{formatUtcDateTime(ev.created_at)}</span>
									</div>
									{#if ev.reason}
										<p class="reason">“{ev.reason}”</p>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
				{/if}
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
	.admin-audit {
		max-width: 760px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.intro {
		color: #6b7280;
		font-size: 0.9rem;
		margin: 8px 0 16px 0;
	}

	.error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #991b1b;
		padding: 10px 14px;
		border-radius: 8px;
		margin-bottom: 16px;
		font-size: 0.875rem;
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

	.entry-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.entry {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 14px 16px;
	}

	.action {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		flex: 0 0 auto;
		margin-top: 2px;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
		background: #fee2e2;
		color: #b91c1c;
	}

	.entry-main {
		min-width: 0;
		flex: 1;
	}

	.line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 5px;
		color: #374151;
	}

	.actor,
	.owner {
		font-weight: 600;
		color: #1f2937;
	}

	.role {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 1px 6px;
		border-radius: 999px;
		background: #e0e7ff;
		color: #4338ca;
	}

	.verb {
		color: #6b7280;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		color: #6b7280;
		font-size: 0.75rem;
		margin-top: 4px;
	}

	.photo {
		font-family: monospace;
	}

	.filename {
		font-style: italic;
	}

	.dot {
		color: #d1d5db;
	}

	.reason {
		margin: 8px 0 0 0;
		color: #4b5563;
		white-space: pre-wrap;
		word-break: break-word;
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
