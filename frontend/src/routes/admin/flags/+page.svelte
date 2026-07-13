<script lang="ts">
	import { Flag as FlagIcon, Check, Trash2, Lock } from 'lucide-svelte';
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
		thumb_url: string | null;
		photo_title: string | null;
		photo_deleted: boolean | null;
	}

	// The photo detail page is keyed by uid = `${source}-${id}`.
	function detailUrl(flag: Flag): string {
		return `/photo/${flag.photo_source}-${flag.photo_id}`;
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

	// Delete a flagged hillview photo outright (moderation delete → notifies the
	// owner with the reason + writes the audit), then resolve the flag.
	let deleteTarget: Flag | null = null;
	let deleteReason = '';
	let deleteBusy = false;

	function openDelete(flag: Flag) {
		deleteTarget = flag;
		deleteReason = '';
	}

	function closeDelete() {
		if (deleteBusy) return;
		deleteTarget = null;
	}

	async function confirmDelete() {
		if (!deleteTarget) return;
		deleteBusy = true;
		error = '';
		try {
			const q = deleteReason.trim() ? `?reason=${encodeURIComponent(deleteReason.trim())}` : '';
			const res = await http.delete(`/photos/${deleteTarget.photo_id}${q}`);
			if (!res.ok) {
				error = `Delete failed (${res.status})`;
				return;
			}
			// The photo is gone; the flag is moot — resolve it too.
			if (!deleteTarget.resolved) {
				await http.post('/flagged/resolve', { flag_id: deleteTarget.id });
			}
			deleteTarget = null;
			await loadFlags();
			await refreshAdminNotifications();
		} catch (e) {
			error = 'Network error deleting photo.';
		} finally {
			deleteBusy = false;
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
								<a class="flag-thumb" href={detailUrl(flag)} data-testid="admin-flag-photo-link" title="Open photo">
									{#if flag.thumb_url}
										<img src={flag.thumb_url} alt="flagged" loading="lazy" data-testid="admin-flag-thumb" />
									{:else}
										<span class="thumb-placeholder"><FlagIcon size={20} /></span>
									{/if}
								</a>
								<div class="flag-main">
									<div class="flag-head">
										<span class="source source-{flag.photo_source}">{flag.photo_source}</span>
										<a class="photo" href={detailUrl(flag)}>{flag.photo_title || `${flag.photo_id.slice(0, 12)}…`}</a>
										{#if flag.photo_deleted}
											<span class="deleted-tag">photo deleted</span>
										{/if}
										<span
											class="status status-{flag.resolved ? 'resolved' : 'open'}"
											data-testid="admin-flag-status"
										>{flag.resolved ? 'resolved' : 'open'}</span>
									</div>
									<div class="meta">flagged {formatUtcDateTime(flag.flagged_at)}</div>
									<p class="reason">{flag.reason ?? '(no reason given)'}</p>
									<div class="actions">
										{#if !flag.resolved}
											<button
												class="action"
												data-testid="admin-flag-resolve"
												disabled={busyId === flag.id}
												on:click={() => resolve(flag)}
											><Check size={14} /> Resolve</button>
										{/if}
										{#if flag.photo_source === 'hillview' && !flag.photo_deleted}
											<button
												class="action danger"
												data-testid="admin-flag-delete"
												disabled={busyId === flag.id}
												on:click={() => openDelete(flag)}
											><Trash2 size={14} /> Delete photo</button>
										{/if}
									</div>
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

{#if deleteTarget}
	<div class="delete-overlay" data-testid="admin-flag-delete-dialog">
		<div class="delete-modal">
			<h3>Delete this photo?</h3>
			<p class="delete-note">
				This removes the photo (a moderation action) and notifies the owner with your
				reason, then resolves the flag. A reason is optional.
			</p>
			<textarea
				class="delete-reason"
				data-testid="admin-flag-delete-reason"
				bind:value={deleteReason}
				rows="3"
				placeholder="Reason (optional) — shown to the owner"
				disabled={deleteBusy}
			></textarea>
			<div class="delete-actions">
				<button class="btn-cancel" data-testid="admin-flag-delete-cancel" on:click={closeDelete} disabled={deleteBusy}>Cancel</button>
				<button class="btn-delete" data-testid="admin-flag-delete-confirm" on:click={confirmDelete} disabled={deleteBusy}>
					{deleteBusy ? 'Deleting…' : 'Delete photo'}
				</button>
			</div>
		</div>
	</div>
{/if}

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
		display: flex;
		align-items: flex-start;
		gap: 14px;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 16px;
	}

	.flag-thumb {
		flex: 0 0 auto;
		width: 72px;
		height: 72px;
		border-radius: 10px;
		overflow: hidden;
		background: #f3f4f6;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.flag-thumb img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		display: block;
	}

	.thumb-placeholder {
		color: #9ca3af;
	}

	.flag-main {
		flex: 1;
		min-width: 0;
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
		font-size: 0.85rem;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 55%;
	}

	.photo:hover {
		text-decoration: underline;
	}

	.deleted-tag {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 2px 6px;
		border-radius: 999px;
		background: #f3f4f6;
		color: #6b7280;
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

	.action.danger {
		border-color: #fecaca;
		color: #b91c1c;
	}

	.action.danger:hover:not(:disabled) {
		background: #fef2f2;
	}

	.delete-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.4);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 130200;
		padding: 16px;
	}

	.delete-modal {
		background: white;
		border-radius: 14px;
		padding: 24px;
		max-width: 440px;
		width: 100%;
		box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
	}

	.delete-modal h3 {
		margin: 0 0 8px 0;
		color: #1f2937;
	}

	.delete-note {
		margin: 0 0 14px 0;
		color: #6b7280;
		font-size: 0.85rem;
	}

	.delete-reason {
		width: 100%;
		box-sizing: border-box;
		padding: 10px 12px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9rem;
		font-family: inherit;
		resize: vertical;
	}

	.delete-actions {
		display: flex;
		justify-content: flex-end;
		gap: 10px;
		margin-top: 16px;
	}

	.btn-cancel,
	.btn-delete {
		padding: 8px 18px;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid #d1d5db;
		background: white;
		color: #374151;
	}

	.btn-delete {
		background: #dc2626;
		border-color: #dc2626;
		color: #fff;
	}

	.btn-delete:disabled,
	.btn-cancel:disabled {
		opacity: 0.6;
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
