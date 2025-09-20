<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { http, handleApiError } from '$lib/http';
	import { myGoto } from '$lib/navigation.svelte';
	import { constructPhotoMapUrl, constructUserPhotosUrl } from '$lib/urlUtils';
	import StandardHeaderWithAlert from '../../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../../components/StandardBody.svelte';
	import Spinner from '../../../components/Spinner.svelte';

	interface UserPhoto {
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
		photos: UserPhoto[];
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
	let photos: UserPhoto[] = [];
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
			console.error('Error loading user photos:', err);
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

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString();
	}

	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleTimeString('en-US', {
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getPhotoUrl(photo: UserPhoto): string {
		return photo.sizes?.['320']?.url || '';
	}

	function viewOnMap(photo: UserPhoto) {
		if (photo.latitude && photo.longitude) {
			myGoto(constructPhotoMapUrl(photo));
		}
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
			<div class="photos-header">
				<h2>{user?.username}'s Photos ({totalCount})</h2>
				<button class="back-button" on:click={() => myGoto('/users')}>
					← Back to Users
				</button>
			</div>

			<div class="photos-grid">
				{#each photos as photo}
					<div class="photo-card"
						 class:clickable={photo.latitude && photo.longitude}
						 on:click={() => viewOnMap(photo)}
						 on:keydown={(e) => e.key === 'Enter' && viewOnMap(photo)}
						 role="button"
						 tabindex={photo.latitude && photo.longitude ? 0 : -1}>
						<div class="photo-image">
							<img
								src={getPhotoUrl(photo)}
								alt={photo.original_filename}
								loading="lazy"
							/>
							{#if photo.processing_status !== 'completed'}
								<div class="processing-badge">
									{photo.processing_status}
								</div>
							{/if}
						</div>
						<div class="photo-info">
							<h3 class="filename">{photo.original_filename}</h3>
							<p class="date">Uploaded: {formatDate(photo.uploaded_at)}</p>
							{#if photo.captured_at}
								<p class="date">Captured: {formatDate(photo.captured_at)}</p>
							{/if}
							{#if photo.latitude && photo.longitude}
								<p class="location">📍 {photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}</p>
							{/if}
							{#if photo.description}
								<p class="description">{photo.description}</p>
							{/if}
						</div>
					</div>
				{/each}
			</div>

			{#if hasMore}
				<div class="load-more-container">
					<button
						class="load-more-button"
						on:click={loadMorePhotos}
						disabled={loadingMore}
					>
						{#if loadingMore}
							<Spinner />
							Loading more...
						{:else}
							Load More Photos
						{/if}
					</button>
				</div>
			{/if}
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

	.photos-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 24px;
		flex-wrap: wrap;
		gap: 16px;
	}

	.photos-header h2 {
		margin: 0;
		color: #444;
		font-size: 1.5rem;
		font-weight: 600;
	}

	.back-button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 16px;
		background-color: #f5f5f5;
		border: 1px solid #ddd;
		border-radius: 4px;
		cursor: pointer;
		font-size: 14px;
		color: #666;
		text-decoration: none;
		transition: background-color 0.2s;
	}

	.back-button:hover {
		background-color: #e5e5e5;
		color: #555;
	}

	.photos-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
		gap: 20px;
		margin-bottom: 32px;
	}

	.photo-card {
		border: 1px solid #eee;
		border-radius: 8px;
		overflow: hidden;
		background: white;
		transition: transform 0.2s ease, box-shadow 0.2s ease;
	}

	.photo-card:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
	}

	.photo-card.clickable {
		cursor: pointer;
	}

	.photo-card.clickable:hover {
		transform: translateY(-4px);
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
	}

	.photo-image {
		position: relative;
		height: 200px;
		overflow: hidden;
		background: #f8f9fa;
	}

	.photo-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.processing-badge {
		position: absolute;
		top: 8px;
		right: 8px;
		background: rgba(255, 193, 7, 0.9);
		color: #333;
		padding: 4px 8px;
		border-radius: 4px;
		font-size: 12px;
		font-weight: 500;
	}

	.photo-info {
		padding: 16px;
	}

	.filename {
		margin: 0 0 8px 0;
		font-size: 1rem;
		font-weight: 600;
		color: #333;
		word-break: break-word;
	}

	.date {
		margin: 0 0 4px 0;
		font-size: 0.85rem;
		color: #666;
	}

	.location {
		margin: 4px 0;
		font-size: 0.85rem;
		color: #28a745;
	}

	.description {
		margin: 8px 0 0 0;
		font-size: 0.9rem;
		color: #555;
		font-style: italic;
	}

	.load-more-container {
		display: flex;
		justify-content: center;
		margin-top: 32px;
	}

	.load-more-button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 24px;
		background-color: #4a90e2;
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 16px;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.3s, transform 0.2s;
		min-width: 160px;
		justify-content: center;
	}

	.load-more-button:hover:not(:disabled) {
		background-color: #357abd;
		transform: translateY(-1px);
	}

	.load-more-button:disabled {
		background-color: #94a3b8;
		cursor: not-allowed;
		transform: none;
	}

	@media (max-width: 768px) {
		.photos-grid {
			grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
			gap: 16px;
		}

		.photos-section {
			padding: 16px;
		}

		.photos-header {
			flex-direction: column;
			align-items: stretch;
		}

		.photos-header h2 {
			text-align: center;
		}
	}

	@media (max-width: 480px) {
		.photos-grid {
			grid-template-columns: 1fr;
		}
	}
</style>