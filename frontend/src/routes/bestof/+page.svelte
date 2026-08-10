<script lang="ts">
	import { auth } from '$lib/auth.svelte';
	import { createSsrBackedLoad } from '$lib/ssrBackedLoad';
	import { http, handleApiError } from '$lib/http';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import LoadMoreButton from '$lib/components/LoadMoreButton.svelte';
	import PhotoItem from '$lib/components/PhotoItem.svelte';
	import PlaceAttribution from '$lib/components/PlaceAttribution.svelte';
	import PhotoHead from '$lib/components/PhotoHead.svelte';
	import { HILLVIEW_BASE_URL } from '$lib/urlUtilsServer';
	import { app } from '$lib/data.svelte';
	import { buildAnnotationSummary, titleUsesPlace, type PhotoAnnotation } from '$lib/photoDisplay';

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

	export let data:
		| { photos?: BestOfPhoto[]; has_more?: boolean; page?: number }
		| undefined = undefined;

	// Which page of the ranking was server-rendered. Only the web build paginates
	// (it is the only one with a +page.server.ts); elsewhere this stays 1 and the
	// prev/next links never appear, because there is no server to render them.
	const pageNo = data?.page ?? 1;
	const prevHref = pageNo > 2 ? `/bestof?page=${pageNo - 1}` : '/bestof';

	let loading = !data?.photos;
	let loadingMore = false;
	let loadMoreFailed = false;
	let loadMoreFailedUserInitiated = false;
	let error = '';
	let photos: BestOfPhoto[] = data?.photos ?? [];
	let hasMorePhotos = data?.has_more ?? false;
	// Pages, not cursors: ONE coordinate system for this route. The lazy-loader
	// walks the same ?page= sequence a crawler follows, so "what comes next" has
	// a single answer and the Next link below can state it exactly — scrolling
	// twice from page 3 makes it point at page 6, with no arithmetic over item
	// counts. (A cursor would resist the list shifting mid-scroll, but this
	// ranking moves slowly and deep pages cost ~20ms, so it bought nothing here
	// and cost a second way of saying where you are. /activity keeps its cursor:
	// there photos arrive at the head constantly, and there is no page paging.)
	let lastLoadedPage = pageNo;

	// Who needs a fetch and who keeps the server-rendered batch — see
	// createSsrBackedLoad (an anonymous visitor keeps it; that is what stopped
	// crawlers rendering this page as a soft 404).
	const syncLoad = createSsrBackedLoad(!!data?.photos, () => void loadPhotos());
	$: syncLoad($auth);

	/** `append` distinguishes a lazy-loaded continuation from the initial load. */
	async function loadPhotos(page = pageNo, append = false, userInitiated = false) {
		try {
			if (append) {
				loadingMore = true;
				loadMoreFailed = false;
				loadMoreFailedUserInitiated = false;
			} else {
				loading = true;
			}
			error = '';

			// A lazy-loaded next page is opportunistic: its failure is shown on the
			// button, so it must not raise the global "Reconnecting…" episode.
			const response = await http.get(`/bestof/photos?page=${page}`, append ? { quiet: true } : {});

			if (!response.ok) {
				throw new Error(`Failed to fetch best photos: ${response.status}`);
			}

			const data = await response.json();
			const newPhotos = data.photos || [];

			hasMorePhotos = data.has_more || false;
			lastLoadedPage = data.page ?? page;
			photos = append ? [...photos, ...newPhotos] : newPhotos;
		} catch (err) {
			console.error('Error loading best-of data:', err);
			// A failed load-more must not replace a page that is already showing a
			// good grid — only a failed FIRST load has nothing to fall back to.
			// Googlebot renders at a very tall viewport, so the lazy-load fires
			// immediately and its request is refused by api.hillview.cz/robots.txt;
			// taking over the page with an error is what Search Console read as a
			// soft 404.
			if (append) {
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
		if (hasMorePhotos && !loadingMore) {
			await loadPhotos(lastLoadedPage + 1, true, userInitiated);
		}
	}

	// The next page nobody has seen yet — exact, because the loader and this link
	// count in the same units.
	$: nextHref = `/bestof?page=${lastLoadedPage + 1}`;

	// How many headings draw on the geocoded place, which decides both whether to
	// credit OpenStreetMap and how to word it: most cards here carry a title of
	// their own, so "Place names ©" would claim those came from OSM too.
	$: placeTitledCount = photos.filter((p) => titleUsesPlace(p)).length;
</script>

<!-- Each page is its own canonical: they hold different photos, so pointing them
     all at /bestof would tell search engines that pages 2+ are duplicates of
     page 1 and drop them — the opposite of why they exist. -->
<PhotoHead
	title={pageNo > 1 ? `Best of, page ${pageNo} - Hillview` : 'Best of - Hillview'}
	description="The best annotated panoramas on Hillview — hilltop views and vistas from places where cars can't go, labeled to help you name what you're looking at."
	ogType="website"
	ogImage={{ url: `${HILLVIEW_BASE_URL}/og-card.png`, width: 1200, height: 630 }}
	canonicalUrl={pageNo > 1 ? `${HILLVIEW_BASE_URL}/bestof?page=${pageNo}` : `${HILLVIEW_BASE_URL}/bestof`}
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
		<!-- Above the grid, not below it: this list lazy-loads, so a credit at the
		     bottom retreats every time the reader reaches it and is never seen. -->
		{#if placeTitledCount}
			<PlaceAttribution
				label={placeTitledCount === photos.length ? 'Place names' : 'Some place names'}
			/>
		{/if}

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

		<!-- The crawl path, and the no-JS path. Real anchors, always in the DOM:
		     Googlebot does not scroll a lazy-loading list to its end, so depth is
		     only reachable by following links. The lazy-loader above usually gets
		     there first for a human — these are the skeleton it is a shortcut for,
		     and what the page degrades to when a load-more fails. -->
		{#if data?.page !== undefined && (pageNo > 1 || hasMorePhotos)}
			<nav class="pagination" data-testid="bestof-pagination">
				{#if pageNo > 1}
					<a href={prevHref} rel="prev" data-testid="bestof-prev-page">← Previous</a>
				{/if}
				<span class="page-no">Page {pageNo}</span>
				{#if hasMorePhotos}
					<a href={nextHref} rel="next" data-testid="bestof-next-page">Next →</a>
				{/if}
			</nav>
		{/if}

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

	.pagination {
		display: flex;
		justify-content: center;
		align-items: baseline;
		gap: 1.5rem;
		padding: 0.5rem 1rem 2rem;
		font-size: 0.95rem;
	}

	.pagination a {
		color: #1565c0;
		text-decoration: none;
		font-weight: 500;
	}

	.pagination a:hover {
		text-decoration: underline;
	}

	.pagination .page-no {
		color: #6c757d;
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
