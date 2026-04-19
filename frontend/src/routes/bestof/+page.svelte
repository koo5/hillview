<script lang="ts">
	import { onMount } from 'svelte';
	import { http, handleApiError } from '$lib/http';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import LoadMoreButton from '$lib/components/LoadMoreButton.svelte';
	import PhotoItem from '$lib/components/PhotoItem.svelte';

	interface BestOfPhoto {
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
		owner_username: string;
		owner_id: string;
		score: number;
	}

	export let data: { photos?: BestOfPhoto[]; has_more?: boolean; next_cursor?: string | null } | undefined = undefined;

	let loading = !data?.photos;
	let loadingMore = false;
	let error = '';
	let photos: BestOfPhoto[] = data?.photos ?? [];
	let hasMorePhotos = data?.has_more ?? false;
	let nextCursor: string | null = data?.next_cursor ?? null;

	onMount(async () => {
		if (!data?.photos) await loadPhotos();
	});

	async function loadPhotos(cursor?: string) {
		try {
			if (cursor) {
				loadingMore = true;
			} else {
				loading = true;
			}
			error = '';

			const url = cursor
				? `/bestof/photos?cursor=${encodeURIComponent(cursor)}`
				: '/bestof/photos';
			const response = await http.get(url);

			if (!response.ok) {
				throw new Error(`Failed to fetch best photos: ${response.status}`);
			}

			const data = await response.json();
			const newPhotos = data.photos || [];

			hasMorePhotos = data.has_more || false;
			nextCursor = data.next_cursor || null;

			if (cursor) {
				photos = [...photos, ...newPhotos];
			} else {
				photos = newPhotos;
			}
		} catch (err) {
			console.error('Error loading best-of data:', err);
			error = handleApiError(err);
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMorePhotos() {
		if (nextCursor && !loadingMore) {
			await loadPhotos(nextCursor);
		}
	}
</script>

<svelte:head>
	<title>Best of - Hillview</title>
</svelte:head>

<StandardHeaderWithAlert
	title="Best of"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	{#if loading}
		<div class="loading-container">
			<Spinner />
			<p>Loading best photos...</p>
		</div>
	{:else if error}
		<div class="error">
			<p>Error loading photos: {error}</p>
			<button on:click={() => loadPhotos()} class="retry-button">
				Try Again
			</button>
		</div>
	{:else if photos.length === 0}
		<div class="empty-state">
			<p>No photos yet.</p>
			<p>Photos will appear here as they receive ratings and annotations.</p>
		</div>
	{:else}
		<div class="photo-grid" data-testid="bestof-photo-grid">
			{#each photos as photo}
				<div class="photo-card" data-testid="bestof-photo-card">
					<PhotoItem
						{photo}
						variant="thumbnail"
						preferDescription={true}
					/>
					<div class="photo-score" data-testid="bestof-photo-score">
						Score: {photo.score}
					</div>
				</div>
			{/each}
		</div>

		<LoadMoreButton
			hasMore={hasMorePhotos && !loading}
			loading={loadingMore}
			onLoadMore={loadMorePhotos}
		/>
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

	.photo-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 1rem;
	}

	.photo-card {
		background: white;
		border-radius: 8px;
		overflow: hidden;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
	}

	.photo-score {
		text-align: center;
		padding: 0.4rem;
		font-size: 0.85rem;
		color: #6c757d;
		font-weight: 500;
	}

	@media (max-width: 768px) {
		.photo-grid {
			grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
			gap: 0.75rem;
		}
	}
</style>
