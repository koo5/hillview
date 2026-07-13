<script lang="ts">
	import { Flag as FlagIcon, Check, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, isModerator, refreshAdminNotifications } from '$lib/adminNotifications';

	interface Flag {
		id: string;
		flagging_user_id: string | null;
		photo_source: string;
		photo_id: string;
		flagged_at: string;
		reason: string | null;
		resolved: boolean;
		resolved_at: string | null;
		resolved_by: string | null;
	}

	let flags: Flag[] = [];
	let loading = false;
	let error = '';
	let filter: 'open' | 'all' = 'open';
	let busyId: string | null = null;

	// Load once the profile confirms moderator/admin (may be false while the profile
	// is still loading), and again whenever the filter changes.
	let loadedOnce = false;
	$: if ($isModerator && !loadedOnce) {
		loadedOnce = true;
		loadFlags();
	}

	async function loadFlags() {
		loading = true;
		error = '';
		try {
			const qs = filter === 'open' ? '?resolved=false&limit=100' : '?limit=100';
			const res = await http.get('/flagged/photos/all' + qs);
			if (!res.ok) {
				error = `Failed to load flags (${res.status})`;
				return;
			}
			const data = await res.json();
			flags = Array.isArray(data) ? data : [];
		} catch (e) {
			error = 'Network error loading flags.';
		} finally {
			loading = false;
		}
	}

	function setFilter(f: 'open' | 'all') {
		if (filter === f) return;
		filter = f;
		loadFlags();
	}

	async function resolve(flag: Flag) {
		busyId = flag.id;
		error = '';
		try {
			const res = await http.post('/flagged/resolve', { flag_id: flag.id });
			if (!res.ok) {
				error = `Resolve failed (${res.status})`;
				return;
			}
			// Refetch (respects the active filter) and refresh the badge count.
			await loadFlags();
			await refreshAdminNotifications();
		} catch (e) {
			error = 'Network error resolving flag.';
		} finally {
			busyId = null;
		}
	}
</script>

<StandardHeaderWithAlert title="Flagged photos" showMenuButton={true} fallbackHref={$isAdmin ? '/admin' : '/moderate'} />

<StandardBody>
	<div class="admin-flags" data-testid="admin-flags-page">
		<ProfileGate>
			{#if $isModerator}
				<div class="toolbar">
					<div class="filters">
						<button
							class="filter"
							class:active={filter === 'open'}
							data-testid="admin-flags-filter-open"
							on:click={() => setFilter('open')}
						>Open</button>
						<button
							class="filter"
							class:active={filter === 'all'}
							data-testid="admin-flags-filter-all"
							on:click={() => setFilter('all')}
						>All</button>
					</div>
				</div>

				{#if error}
					<div class="error" data-testid="admin-flags-error">{error}</div>
				{/if}

				{#if loading && flags.length === 0}
					<div class="empty">Loading…</div>
				{:else if flags.length === 0}
					<div class="empty" data-testid="admin-flags-empty">
						<FlagIcon size={24} />
						<p>{filter === 'open' ? 'No open flags. Nothing to review.' : 'No flags yet.'}</p>
					</div>
				{:else}
					<ul class="flag-list">
						{#each flags as flag (flag.id)}
							<li
								class="flag"
								data-testid="admin-flag"
								data-flag-id={flag.id}
								data-photo-id={flag.photo_id}
								data-source={flag.photo_source}
							>
								<div class="flag-head">
									<span class="source source-{flag.photo_source}">{flag.photo_source}</span>
									<span class="photo" title={`photo ${flag.photo_id}`}>{flag.photo_id.slice(0, 12)}…</span>
									<span
										class="status status-{flag.resolved ? 'resolved' : 'open'}"
										data-testid="admin-flag-status"
									>{flag.resolved ? 'resolved' : 'open'}</span>
								</div>
								<div class="meta">flagged {formatUtcDateTime(flag.flagged_at)}</div>
								<p class="reason">{flag.reason ?? '(no reason given)'}</p>
								{#if !flag.resolved}
									<div class="actions">
										<button
											class="action"
											data-testid="admin-flag-resolve"
											disabled={busyId === flag.id}
											on:click={() => resolve(flag)}
										><Check size={14} /> Resolve</button>
									</div>
								{/if}
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
	.admin-flags {
		max-width: 760px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.toolbar {
		display: flex;
		justify-content: flex-end;
		margin: 8px 0 16px 0;
	}

	.filters {
		display: inline-flex;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		overflow: hidden;
	}

	.filter {
		padding: 6px 16px;
		background: white;
		border: none;
		cursor: pointer;
		font-size: 0.875rem;
		color: #4b5563;
	}

	.filter.active {
		background: #4f46e5;
		color: white;
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

	.flag-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.flag {
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 16px;
	}

	.flag-head {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.source {
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
		background: #ede9fe;
		color: #6d28d9;
	}

	.photo {
		font-family: monospace;
		font-size: 0.8rem;
		color: #4b5563;
	}

	.status {
		margin-left: auto;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
	}

	.status-open {
		background: #fee2e2;
		color: #b91c1c;
	}

	.status-resolved {
		background: #dcfce7;
		color: #15803d;
	}

	.meta {
		color: #6b7280;
		font-size: 0.75rem;
		margin-top: 6px;
	}

	.reason {
		margin: 10px 0;
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.actions {
		display: flex;
		gap: 8px;
	}

	.action {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 6px 12px;
		border: 1px solid #d1d5db;
		background: white;
		border-radius: 8px;
		font-size: 0.8rem;
		color: #374151;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.action:hover:not(:disabled) {
		background: #f3f4f6;
	}

	.action:disabled {
		opacity: 0.5;
		cursor: default;
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
