<script lang="ts">
	import { auth } from '$lib/auth.svelte';
	import { createSsrBackedLoad } from '$lib/ssrBackedLoad';
	import { http, handleApiError } from '$lib/http';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import LoadMoreButton from '$lib/components/LoadMoreButton.svelte';
	import PhotoItem from '$lib/components/PhotoItem.svelte';
	import PhotoHead from '$lib/components/PhotoHead.svelte';
	import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
	import { app } from '$lib/data.svelte';
	import { buildAnnotationSummary, type PhotoAnnotation } from '$lib/photoDisplay';

	interface BestOfPhoto {
		id: string;
		original_filename: string;
		title?: string;
		place_name?: string | null;
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
		annotation_count: number;
		annotations?: string[];
	}

	// One line naming what each panorama shows — this page is the index of
	// views, so the labels are its real content (for readers and crawlers
	// alike; the count alone carries none of it). Longer budget than the meta
	// description: grid cards have the room.
	function photoSummary(photo: BestOfPhoto): string {
		const anns = (photo.annotations ?? []).map(
			(body, i) => ({ id: String(i), body, owner_username: null, created_at: null }) as PhotoAnnotation
		);
		return buildAnnotationSummary(anns, 220);
	}

	export let data: { photos?: BestOfPhoto[]; has_more?: boolean; next_cursor?: string | null } | undefined = undefined;

	let loading = !data?.photos;
	let loadingMore = false;
	let loadMoreFailed = false;
	let loadMoreFailedUserInitiated = false;
	let error = '';
	let photos: BestOfPhoto[] = data?.photos ?? [];
	let hasMorePhotos = data?.has_more ?? false;
	let nextCursor: string | null = data?.next_cursor ?? null;

	// Who needs a fetch and who keeps the server-rendered batch — see
	// createSsrBackedLoad (an anonymous visitor keeps it; that is what stopped
	// crawlers rendering this page as a soft 404).
	const syncLoad = createSsrBackedLoad(!!data?.photos, () => void loadPhotos());
	$: syncLoad($auth);

	async function loadPhotos(cursor?: string, userInitiated = false) {
		try {
			if (cursor) {
				loadingMore = true;
				loadMoreFailed = false;
				loadMoreFailedUserInitiated = false;
			} else {
				loading = true;
			}
			error = '';

			const url = cursor
				? `/bestof/photos?cursor=${encodeURIComponent(cursor)}`
				: '/bestof/photos';
			// A lazy-loaded next page is opportunistic: its failure is shown on the
			// button, so it must not raise the global "Reconnecting…" episode.
			const response = await http.get(url, cursor ? { quiet: true } : {});

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
			// A failed load-more must not replace a page that is already showing a
			// good grid — only a failed FIRST load has nothing to fall back to.
			// Googlebot renders at a very tall viewport, so the lazy-load fires
			// immediately and its request is refused by api.hillview.cz/robots.txt;
			// taking over the page with an error is what Search Console read as a
			// soft 404.
			if (cursor) {
				loadMoreFailed = true;
				loadMoreFailedUserInitiated = userInitiated;
			} else {
				error = handleApiError(err);
			}
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMorePhotos(userInitiated = false) {
		if (nextCursor && !loadingMore) {
			await loadPhotos(nextCursor, userInitiated);
		}
	}
</script>

<PhotoHead
	title="Best of - Hillview"
	description="The best annotated panoramas on Hillview — hilltop views and vistas from places where cars can't go, labeled to help you name what you're looking at."
	ogType="website"
	ogImage={{ url: `${HILLVIEW_BASE_URL}/og-card.png`, width: 1200, height: 630 }}
	canonicalUrl={`${HILLVIEW_BASE_URL}/bestof`}
/>

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
						preferTitle={true}
					/>
					{#if photoSummary(photo)}
						<p class="annotation-summary" data-testid="bestof-annotation-summary">
							{photoSummary(photo)}
						</p>
					{/if}
					<div class="photo-score" data-testid="bestof-photo-stats">
						{photo.annotation_count} annotation{photo.annotation_count === 1 ? '' : 's'}{#if $app.debug_enabled}
							· Score: {photo.score}{/if}
					</div>
				</div>
			{/each}
		</div>

		<LoadMoreButton
			hasMore={hasMorePhotos && !loading}
			loading={loadingMore}
			failed={loadMoreFailed}
			failedUserInitiated={loadMoreFailedUserInitiated}
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

	.annotation-summary {
		margin: 0;
		padding: 0.4rem 0.6rem 0;
		font-size: 0.85rem;
		color: #444;
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
