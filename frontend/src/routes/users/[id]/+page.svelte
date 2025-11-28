<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { http, handleApiError } from '$lib/http';
	import { constructUserPhotosUrl } from '$lib/urlUtils';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import PhotoItem from '$lib/components/PhotoItem.svelte';
	import LoadMoreButton from '$lib/components/LoadMoreButton.svelte';

	interface UsersPhotosItem {
		id: string;
		original_filename: string;
		uploaded_at: string;
		captured_at?: string;
		processing_status: string;
		latitude?: number;
		longitude?: number;
		bearing?: number;
		width?: number;
		height?: number;
		sizes?: Record<string, { path: string; url: string; width: number; height: number }>;
		description?: string;
	}

	interface User {
		id: string;
		username: string;
	}

	interface PhotosResponse {
		photos: UsersPhotosItem[];
		user: User;
		pagination: {
			next_cursor: string | null;
			has_more: boolean;
		};
		counts: {
			total: number;
		};
	}

	let userId: string;
	let photos: UsersPhotosItem[] = [];
	let user: User | null = null;
	let loading = true;
	let loadingMore = false;
	let error = '';
	let nextCursor: string | null = null;
	let hasMore = false;
	let totalCount = 0;

	// React to route parameter changes
	$: userId = $page.params.id;
	$: if (userId) {
		loadUserPhotos(true);
	}

	onMount(() => {
		if (userId) {
			loadUserPhotos(true);
		}
	});

	async function loadUserPhotos(reset = false) {
		try {
			if (reset) {
				loading = true;
				photos = [];
				nextCursor = null;
				hasMore = false;
				totalCount = 0;
			} else {
				loadingMore = true;
			}
			error = '';

			const url = constructUserPhotosUrl(userId, nextCursor || undefined);

			const response = await http.get(url);

			if (!response.ok) {
				throw new Error(`Failed to fetch user photos: ${response.status}`);
			}

			const data: PhotosResponse = await response.json();

			if (reset) {
				photos = data.photos;
				user = data.user;
			} else {
				photos = [...photos, ...data.photos];
			}

			nextCursor = data.pagination.next_cursor;
			hasMore = data.pagination.has_more;
			totalCount = data.counts.total;

		} catch (err) {
			console.error('🢄Error loading user photos:', err);
			error = handleApiError(err);
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMorePhotos() {
		if (!hasMore || loadingMore) return;
		await loadUserPhotos(false);
	}

</script>

<svelte:head>
	<title>{user ? `${user.username} - Photos` : 'User Photos'} - Hillview</title>
</svelte:head>

<StandardHeaderWithAlert
	title={user ? `${user.username}'s Photos` : 'User Photos'}
	showMenuButton={true}
	fallbackHref="/users"
/>

<StandardBody>
	{#if loading}
		<div class="loading-container">
			<Spinner />
			<p>Loading user photos...</p>
		</div>
	{:else if error}
		<div class="error">
			<p>Error loading user photos: {error}</p>
			<button on:click={() => loadUserPhotos(true)} class="retry-button">
				Try Again
			</button>
		</div>
	{:else if photos.length === 0}
		<div class="empty-state">
			<p>No photos found.</p>
			{#if user}
				<p>{user.username} hasn't uploaded any photos yet.</p>
			{/if}
		</div>
	{:else}
		<div class="photos-section">
			<h2>{user?.username}'s Photos ({totalCount})</h2>

			<div class="photos-grid">
				{#each photos as photo}
					<PhotoItem
						{photo}
						variant="card"
						showDates={true}
						showTime={false}
						showDescription={true}
					/>
				{/each}
			</div>

			<LoadMoreButton
				hasMore={hasMore && !loading}
				loading={loadingMore}
				onLoadMore={loadMorePhotos}
			/>
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

	.photos-section {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
	}

	.photos-section h2 {
		margin: 0 0 24px 0;
		color: #444;
		font-size: 1.5rem;
		font-weight: 600;
	}

	.photos-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 20px;
		margin-bottom: 32px;
	}



	@media (max-width: 768px) {
		.photos-grid {
			grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
			gap: 16px;
		}

		.photos-section {
			padding: 16px;
		}

		.photos-section h2 {
			text-align: center;
		}
	}

	@media (max-width: 480px) {
		.photos-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
