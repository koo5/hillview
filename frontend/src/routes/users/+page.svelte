<script lang="ts">
	import { onMount } from 'svelte';
	import { http, handleApiError } from '$lib/http';
	import { myGoto } from '$lib/navigation.svelte';
	import { constructUserProfileUrl } from '$lib/urlUtils';
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import Spinner from '../../components/Spinner.svelte';

	interface User {
		id: string;
		username: string;
		photo_count: number;
		latest_photo_at?: string;
		latest_photo_url?: string;
	}

	let users: User[] = [];
	let loading = true;
	let error = '';

	onMount(async () => {
		await loadUsers();
	});

	async function loadUsers() {
		try {
			loading = true;
			error = '';

			const response = await http.get('/users/');

			if (!response.ok) {
				throw new Error(`Failed to fetch users: ${response.status}`);
			}

			const data = await response.json();
			users = data;

		} catch (err) {
			console.error('🢄Error loading users:', err);
			error = handleApiError(err);
		} finally {
			loading = false;
		}
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const diffInDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

		if (diffInDays === 0) {
			return 'Today';
		} else if (diffInDays === 1) {
			return 'Yesterday';
		} else if (diffInDays < 7) {
			return `${diffInDays} days ago`;
		} else {
			return date.toLocaleDateString();
		}
	}

	function viewUserPhotos(userId: string) {
		myGoto(constructUserProfileUrl(userId));
	}
</script>

<svelte:head>
	<title>Users - Hillview</title>
</svelte:head>

<StandardHeaderWithAlert
	title="Users"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	{#if loading}
		<div class="loading-container">
			<Spinner />
			<p>Loading users...</p>
		</div>
	{:else if error}
		<div class="error">
			<p>Error loading users: {error}</p>
			<button on:click={loadUsers} class="retry-button">
				Try Again
			</button>
		</div>
	{:else if users.length === 0}
		<div class="empty-state">
			<p>No users found.</p>
		</div>
	{:else}
		<div class="users-grid">
			<h2>All Users ({users.length})</h2>

			<div class="grid">
				{#each users as user}
					<div class="user-card"
						data-testid={`user-card-${user.username}`}
						on:click={() => viewUserPhotos(user.id)}
						on:keydown={(e) => e.key === 'Enter' && viewUserPhotos(user.id)}
						role="button"
						tabindex="0">
						<div class="user-photo">
							{#if user.latest_photo_url}
								<img
									src={user.latest_photo_url}
									alt="{user.username}'s latest photo"
									loading="lazy"
								/>
							{:else}
								<div class="no-photo">
									<span>📷</span>
								</div>
							{/if}
						</div>
						<div class="user-info">
							<h3 class="username">{user.username}</h3>
							<p class="photo-count">{user.photo_count} photo{user.photo_count !== 1 ? 's' : ''}</p>
							{#if user.latest_photo_at}
								<p class="latest-activity">Latest: {formatDate(user.latest_photo_at)}</p>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</StandardBody>

<style>
	.loading-container {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 0;
		gap: 1rem;
	}

	.error {
		text-align: center;
		padding: 2rem;
		background: white;
		border-radius: 8px;
		border: 1px solid #dc3545;
		color: #dc3545;
	}

	.retry-button {
		background: #dc3545;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 4px;
		cursor: pointer;
		margin-top: 1rem;
	}

	.retry-button:hover {
		background: #c82333;
	}

	.empty-state {
		text-align: center;
		padding: 4rem 2rem;
		background: white;
		border-radius: 8px;
		color: #666;
	}

	.users-grid {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
	}

	.users-grid h2 {
		margin: 0 0 24px 0;
		color: #444;
		font-size: 1.5rem;
		font-weight: 600;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 20px;
	}

	.user-card {
		border: 1px solid #eee;
		border-radius: 8px;
		overflow: hidden;
		cursor: pointer;
		transition: transform 0.2s ease, box-shadow 0.2s ease;
		background: white;
	}

	.user-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
	}

	.user-photo {
		height: 150px;
		overflow: hidden;
		background: #f8f9fa;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.user-photo img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.no-photo {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #6c757d;
		font-size: 2rem;
	}

	.user-info {
		padding: 16px;
	}

	.username {
		margin: 0 0 8px 0;
		font-size: 1.1rem;
		font-weight: 600;
		color: #333;
	}

	.photo-count {
		margin: 0 0 4px 0;
		font-size: 0.9rem;
		color: #666;
	}

	.latest-activity {
		margin: 0;
		font-size: 0.8rem;
		color: #999;
	}

	@media (max-width: 768px) {
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
			gap: 16px;
		}

		.users-grid {
			padding: 16px;
		}
	}

	@media (max-width: 480px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}
</style>