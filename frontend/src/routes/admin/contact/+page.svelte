<script lang="ts">
	import { Mail, Check, Reply, Archive, User as UserIcon, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, refreshAdminNotifications } from '$lib/adminNotifications';

	interface ContactMessage {
		id: number;
		contact_info: string;
		message: string;
		user_id: string | null;
		created_at: string;
		status: string;
		admin_notes: string | null;
		replied_at: string | null;
		replied_by: string | null;
		ip_address: string | null;
	}

	let messages: ContactMessage[] = [];
	let loading = false;
	let error = '';
	let filter: 'all' | 'new' = 'new';
	let busyId: number | null = null;

	// Load once the profile confirms admin (isAdmin may be false while the profile
	// is still loading), and again whenever the filter changes.
	let loadedOnce = false;
	$: if ($isAdmin && !loadedOnce) {
		loadedOnce = true;
		loadMessages();
	}

	async function loadMessages() {
		loading = true;
		error = '';
		try {
			const qs = filter === 'new' ? '?status_filter=new&limit=100' : '?limit=100';
			const res = await http.get('/admin/contact/messages' + qs);
			if (!res.ok) {
				error = `Failed to load messages (${res.status})`;
				return;
			}
			const data = await res.json();
			messages = data.messages ?? [];
		} catch (e) {
			error = 'Network error loading messages.';
		} finally {
			loading = false;
		}
	}

	function setFilter(f: 'all' | 'new') {
		if (filter === f) return;
		filter = f;
		loadMessages();
	}

	async function setStatus(msg: ContactMessage, status: string) {
		busyId = msg.id;
		error = '';
		try {
			const res = await http.patch(`/admin/contact/messages/${msg.id}`, { status });
			if (!res.ok) {
				error = `Update failed (${res.status})`;
				return;
			}
			// Refetch (respects the active filter) and refresh the badge count.
			await loadMessages();
			await refreshAdminNotifications();
		} catch (e) {
			error = 'Network error updating message.';
		} finally {
			busyId = null;
		}
	}

</script>

<StandardHeaderWithAlert title="Contact messages" showMenuButton={true} fallbackHref="/admin" />

<StandardBody>
	<div class="admin-contact" data-testid="admin-contact-page">
		<ProfileGate>
			{#if $isAdmin}
				<div class="toolbar">
					<div class="filters">
						<button
							class="filter"
							class:active={filter === 'new'}
							data-testid="admin-contact-filter-new"
							on:click={() => setFilter('new')}
						>New</button>
						<button
							class="filter"
							class:active={filter === 'all'}
							data-testid="admin-contact-filter-all"
							on:click={() => setFilter('all')}
						>All</button>
					</div>
				</div>

				{#if error}
					<div class="error" data-testid="admin-contact-error">{error}</div>
				{/if}

				{#if loading && messages.length === 0}
					<div class="empty">Loading…</div>
				{:else if messages.length === 0}
					<div class="empty" data-testid="admin-contact-empty">
						<Mail size={24} />
						<p>{filter === 'new' ? 'No new messages. All caught up.' : 'No messages yet.'}</p>
					</div>
				{:else}
					<ul class="message-list">
						{#each messages as msg (msg.id)}
							<li class="message" data-testid="admin-contact-message" data-message-id={msg.id}>
								<div class="message-head">
									<span class="contact-info">{msg.contact_info}</span>
									<span class="status status-{msg.status}" data-testid="admin-contact-status">{msg.status}</span>
								</div>
								<div class="meta">
									<span>{formatUtcDateTime(msg.created_at)}</span>
									<span class="dot">·</span>
									{#if msg.user_id}
										<span class="user"><UserIcon size={12} /> registered user</span>
									{:else}
										<span class="user guest">guest</span>
									{/if}
									{#if msg.ip_address}
										<span class="dot">·</span>
										<span class="ip">{msg.ip_address}</span>
									{/if}
								</div>
								<p class="body">{msg.message}</p>
								<div class="actions">
									<button
										class="action"
										data-testid="admin-contact-mark-read"
										disabled={busyId === msg.id || msg.status === 'read'}
										on:click={() => setStatus(msg, 'read')}
									><Check size={14} /> Mark read</button>
									<button
										class="action"
										data-testid="admin-contact-mark-replied"
										disabled={busyId === msg.id || msg.status === 'replied'}
										on:click={() => setStatus(msg, 'replied')}
									><Reply size={14} /> Mark replied</button>
									<button
										class="action"
										data-testid="admin-contact-archive"
										disabled={busyId === msg.id || msg.status === 'archived'}
										on:click={() => setStatus(msg, 'archived')}
									><Archive size={14} /> Archive</button>
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
	.admin-contact {
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

	.message-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.message {
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 16px;
	}

	.message-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
	}

	.contact-info {
		font-weight: 600;
		color: #1f2937;
		word-break: break-all;
	}

	.status {
		flex: 0 0 auto;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
	}

	.status-new {
		background: #fee2e2;
		color: #b91c1c;
	}

	.status-read {
		background: #e5e7eb;
		color: #374151;
	}

	.status-replied {
		background: #dcfce7;
		color: #15803d;
	}

	.status-archived {
		background: #f3f4f6;
		color: #9ca3af;
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

	.meta .user {
		display: inline-flex;
		align-items: center;
		gap: 3px;
	}

	.meta .guest {
		font-style: italic;
	}

	.dot {
		color: #d1d5db;
	}

	.body {
		margin: 12px 0;
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
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
