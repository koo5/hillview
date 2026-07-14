<script lang="ts">
	import { Users as UsersIcon, Trash2, Ban, RotateCcw, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { auth } from '$lib/authStore';
	import { isAdmin } from '$lib/adminNotifications';

	interface AdminUser {
		id: string;
		username: string | null;
		email: string | null;
		role: string;
		is_active: boolean;
		is_verified: boolean;
		oauth_provider: string | null;
		created_at: string;
		photo_count: number | null;
	}

	const ROLES = ['user', 'moderator', 'admin'];

	let users: AdminUser[] = [];
	let loading = false;
	let error = '';
	let search = '';
	let busyId: string | null = null;
	let searchTimer: ReturnType<typeof setTimeout> | null = null;

	$: selfId = $auth.user?.id;

	let loadedOnce = false;
	$: if ($isAdmin && !loadedOnce) {
		loadedOnce = true;
		loadUsers();
	}

	async function loadUsers() {
		loading = true;
		error = '';
		try {
			const qs = search.trim() ? `?search=${encodeURIComponent(search.trim())}&limit=200` : '?limit=200';
			const res = await http.get('/admin/users' + qs);
			if (!res.ok) {
				error = `Failed to load users (${res.status})`;
				return;
			}
			users = (await res.json()).users ?? [];
		} catch (e) {
			error = 'Network error loading users.';
		} finally {
			loading = false;
		}
	}

	function onSearchInput() {
		if (searchTimer) clearTimeout(searchTimer);
		searchTimer = setTimeout(loadUsers, 300);
	}

	async function patchUser(u: AdminUser, body: Record<string, unknown>) {
		busyId = u.id;
		error = '';
		try {
			const res = await http.patch(`/admin/users/${u.id}`, body);
			if (!res.ok) {
				const detail = await res.json().then((d) => d.detail).catch(() => null);
				error = detail || `Update failed (${res.status})`;
				await loadUsers(); // revert any optimistic UI
				return;
			}
			const updated = await res.json();
			users = users.map((x) => (x.id === u.id ? { ...x, ...updated } : x));
		} catch (e) {
			error = 'Network error updating user.';
		} finally {
			busyId = null;
		}
	}

	function changeRole(u: AdminUser, e: Event) {
		const role = (e.target as HTMLSelectElement).value;
		if (role !== u.role) patchUser(u, { role });
	}

	function toggleActive(u: AdminUser) {
		patchUser(u, { is_active: !u.is_active });
	}

	// Delete flow
	let deleteTarget: AdminUser | null = null;
	let deleteReason = '';
	let deleteBusy = false;

	function openDelete(u: AdminUser) {
		deleteTarget = u;
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
			const res = await http.delete(`/admin/users/${deleteTarget.id}${q}`);
			if (!res.ok) {
				const detail = await res.json().then((d) => d.detail).catch(() => null);
				error = detail || `Delete failed (${res.status})`;
				return;
			}
			users = users.filter((x) => x.id !== deleteTarget!.id);
			deleteTarget = null;
		} catch (e) {
			error = 'Network error deleting user.';
		} finally {
			deleteBusy = false;
		}
	}
</script>

<StandardHeaderWithAlert title="User management" showMenuButton={true} fallbackHref="/admin" />

<StandardBody>
	<div class="admin-users" data-testid="admin-users-page">
		<ProfileGate>
			{#if $isAdmin}
				<div class="toolbar">
					<input
						class="search"
						data-testid="admin-users-search"
						type="search"
						placeholder="Search username or email…"
						bind:value={search}
						on:input={onSearchInput}
					/>
				</div>

				{#if error}
					<div class="error" data-testid="admin-users-error">{error}</div>
				{/if}

				{#if loading && users.length === 0}
					<div class="empty">Loading…</div>
				{:else if users.length === 0}
					<div class="empty" data-testid="admin-users-empty">
						<UsersIcon size={24} />
						<p>No users found.</p>
					</div>
				{:else}
					<ul class="user-list">
						{#each users as u (u.id)}
							<li
								class="user"
								class:suspended={!u.is_active}
								data-testid="admin-user-row"
								data-user-id={u.id}
								data-username={u.username}
								data-role={u.role}
							>
								<div class="user-main">
									<div class="user-head">
										<a class="username" href={`/users/${u.id}`}>{u.username ?? '(no name)'}</a>
										{#if u.id === selfId}<span class="self-tag" data-testid="admin-user-self">you</span>{/if}
										{#if !u.is_active}
											<span class="status suspended-tag" data-testid="admin-user-status">suspended</span>
										{/if}
									</div>
									<div class="user-meta">
										<span>{u.email ?? 'no email'}</span>
										{#if u.oauth_provider}<span class="dot">·</span><span>{u.oauth_provider}</span>{/if}
										<span class="dot">·</span>
										<span>{u.photo_count ?? 0} photos</span>
										<span class="dot">·</span>
										<span>joined {formatUtcDateTime(u.created_at)}</span>
									</div>
								</div>

								<div class="user-actions">
									{#if u.id === selfId}
										<span class="role-static">{u.role}</span>
									{:else}
										<select
											class="role-select"
											data-testid="admin-user-role-select"
											value={u.role}
											disabled={busyId === u.id}
											on:change={(e) => changeRole(u, e)}
										>
											{#each ROLES as r}
												<option value={r}>{r}</option>
											{/each}
										</select>
										<button
											class="action"
											data-testid="admin-user-suspend"
											disabled={busyId === u.id}
											on:click={() => toggleActive(u)}
										>
											{#if u.is_active}<Ban size={14} /> Suspend{:else}<RotateCcw size={14} /> Reactivate{/if}
										</button>
										<button
											class="action danger"
											data-testid="admin-user-delete"
											disabled={busyId === u.id}
											on:click={() => openDelete(u)}
										><Trash2 size={14} /> Delete</button>
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

{#if deleteTarget}
	<div class="delete-overlay" data-testid="admin-user-delete-dialog">
		<div class="delete-modal">
			<h3>Delete “{deleteTarget.username}”?</h3>
			<p class="delete-note">
				This permanently removes the account and cascades their photos and annotations.
				This cannot be undone. A reason is optional (recorded in the audit).
			</p>
			<textarea
				class="delete-reason"
				data-testid="admin-user-delete-reason"
				bind:value={deleteReason}
				rows="2"
				placeholder="Reason (optional)"
				disabled={deleteBusy}
			></textarea>
			<div class="delete-actions">
				<button class="btn-cancel" data-testid="admin-user-delete-cancel" on:click={closeDelete} disabled={deleteBusy}>Cancel</button>
				<button class="btn-delete" data-testid="admin-user-delete-confirm" on:click={confirmDelete} disabled={deleteBusy}>
					{deleteBusy ? 'Deleting…' : 'Delete user'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.admin-users {
		max-width: 900px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.toolbar {
		margin: 8px 0 16px 0;
	}

	.search {
		width: 100%;
		max-width: 360px;
		box-sizing: border-box;
		padding: 8px 12px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9rem;
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

	.user-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.user {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 12px 16px;
	}

	.user.suspended {
		background: #f9fafb;
		opacity: 0.85;
	}

	.user-main {
		min-width: 0;
		flex: 1;
	}

	.user-head {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.username {
		font-weight: 600;
		color: #1f2937;
		text-decoration: none;
	}

	.username:hover {
		text-decoration: underline;
	}

	.self-tag {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 1px 6px;
		border-radius: 999px;
		background: #e0e7ff;
		color: #4338ca;
	}

	.status {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 2px 8px;
		border-radius: 999px;
	}

	.suspended-tag {
		background: #fee2e2;
		color: #b91c1c;
	}

	.user-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		color: #6b7280;
		font-size: 0.75rem;
		margin-top: 4px;
	}

	.dot {
		color: #d1d5db;
	}

	.user-actions {
		display: flex;
		align-items: center;
		gap: 8px;
		flex: 0 0 auto;
	}

	.role-select {
		padding: 6px 8px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.8rem;
		background: white;
		text-transform: capitalize;
	}

	.role-static {
		font-size: 0.8rem;
		color: #6b7280;
		text-transform: capitalize;
		padding: 0 6px;
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
</style>
