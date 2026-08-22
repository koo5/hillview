<script lang="ts">
	import { formatDate, type PhotoAnnotation, type PublicPhoto } from '$lib/photoDisplay';
	import { parseAnnotationBody, type BodyItem } from '$lib/utils/annotationBody';
	import { constructMapUrl } from '$lib/urlUtils';
	import { targetRectNormalized, rectToViewBounds } from '$zoomview/annotationTargets';

	export let annotations: PhotoAnnotation[] = [];
	export let heading: string = 'Annotations';
	// The photo the annotations belong to — needed to mint the per-annotation
	// links into the interactive viewer. Optional: without it the rows still
	// render, just without the deep links.
	export let photo: PublicPhoto | null = null;

	// Same zoom as the coordinate links in the zoomview's annotation menu.
	const COORDS_MAP_ZOOM = 16;

	function coordsUrl(lat: number, lon: number): string {
		return constructMapUrl({ lat, lon, zoom: COORDS_MAP_ZOOM });
	}

	/** Deep link opening the interactive viewer zoomed to this annotation's
	 *  target — the same x1..y2 URL contract /shared/ links use, so the map
	 *  homepage needs no changes to honour it. Null when the annotation has no
	 *  usable target or the photo lacks the needed metadata. */
	function annotationViewUrl(a: PhotoAnnotation): string | null {
		if (!photo || photo.latitude == null || photo.longitude == null) return null;
		if (!photo.width || !photo.height) return null;
		const rect = targetRectNormalized(a.target as Record<string, unknown> | null);
		if (!rect) return null;
		const bounds = rectToViewBounds(rect, photo.width, photo.height);
		if (!bounds) return null;
		return constructMapUrl({
			lat: photo.latitude,
			lon: photo.longitude,
			bearing: photo.bearing ?? undefined,
			photoUid: photo.uid,
			zoom: 20,
			zoomViewBounds: bounds
		});
	}

	function labelIndex(items: BodyItem[]): number {
		return items.findIndex((it) => it.type === 'text');
	}
</script>

{#if annotations.length > 0}
	<section class="annotations" data-testid="photo-annotations">
		<h2>{heading}</h2>
		<ul>
			{#each annotations as a (a.id)}
				{@const items = parseAnnotationBody(a.body ?? '')}
				{@const viewUrl = annotationViewUrl(a)}
				{@const labelIdx = labelIndex(items)}
				<li class="annotation" data-testid="photo-annotation">
					<div class="body" data-testid="photo-annotation-body">
						{#each items as item, i}
							{#if item.type === 'url'}
								<a
									class="segment ref"
									href={item.value}
									title={item.value}
									rel="ugc nofollow noopener"
									target="_blank">{item.display}</a
								>
							{:else if item.type === 'coords'}
								<!-- Same clickability the zoomview annotation menu gives body
								     coordinates; a plain in-app anchor here — this is a normal
								     page, not a modal, so the new-tab rationale doesn't apply. -->
								<a
									class="segment coords"
									href={coordsUrl(item.lat, item.lon)}
									data-testid="photo-annotation-coords">{item.value}</a
								>
							{:else if i === labelIdx && viewUrl}
								<a
									class="segment label"
									href={viewUrl}
									title="Show this annotation in the panorama"
									data-testid="photo-annotation-locate">{item.value}</a
								>
							{:else}
								<span class="segment" class:label={i === labelIdx}>{item.value}</span>
							{/if}
						{/each}
					</div>
					<p class="attribution">
						{#if a.owner_username}
							<a href={`/users/${a.owner_username}`} data-testid="photo-annotation-owner"
								>@{a.owner_username}</a
							>
						{/if}
						{#if a.created_at}
							<span class="date" data-testid="photo-annotation-date">{formatDate(a.created_at)}</span>
						{/if}
					</p>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	.annotations {
		margin-top: 1.5rem;
		border-top: 1px solid #eee;
		padding-top: 1rem;
	}

	.annotations h2 {
		font-size: 1.1rem;
		margin: 0 0 0.75rem 0;
	}

	.annotations ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.annotation {
		padding: 0.5rem 0;
		border-bottom: 1px solid #f1f1f1;
	}

	.annotation:last-child {
		border-bottom: none;
	}

	.annotation .body {
		margin: 0;
		word-break: break-word;
	}

	/* Each pipe-separated segment on its own line */
	.segment {
		display: block;
	}

	.segment.label {
		font-weight: 600;
		color: #222;
	}

	a.segment {
		text-decoration: none;
		width: fit-content;
	}

	a.segment:hover {
		text-decoration: underline;
	}

	.segment.ref,
	.segment.coords {
		font-size: 0.85rem;
		color: #1565c0;
	}

	a.segment.label {
		color: #1565c0;
	}

	/* Attribution deliberately quiet — the labels are the content here,
	   authorship is a footnote. */
	.annotation .attribution {
		margin: 2px 0 0 0;
		font-size: 0.75rem;
		color: #a5adb5;
	}

	.annotation .attribution a {
		color: inherit;
		text-decoration: none;
	}

	.annotation .attribution a:hover {
		text-decoration: underline;
	}

	.annotation .date {
		margin-left: 0.5rem;
	}
</style>
