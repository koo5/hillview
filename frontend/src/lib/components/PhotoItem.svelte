<script lang="ts">
	import { constructPhotoMapUrl } from '$lib/urlUtils';
	import { app } from '$lib/data.svelte';
	import type { PhotoItemData } from '$lib/types/photoItemTypes';
	import { ChevronDown } from 'lucide-svelte';

	// Props
	export let photo: PhotoItemData;
	export let variant: 'card' | 'thumbnail' = 'card';
	export let showDates = true;
	export let showDescription = true;

	// State
	let detailsExpanded = false;

	// Helper functions
	function formatDateTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatTime(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getPhotoUrl(photo: PhotoItemData): string {
		return photo.sizes?.['320']?.url || '';
	}

	function getMapUrl(photo: PhotoItemData): string | null {
		if (photo.latitude && photo.longitude) {
			return constructPhotoMapUrl(photo);
		}
		return null;
	}

	function handleImageClick(e: MouseEvent) {
		if (!mapUrl) {
			e.preventDefault();
			return;
		}
		app.update(a => ({ ...a, activity: 'view' }));
		// Navigation is handled by the anchor tag, alerts cleared by layout's beforeNavigate
	}

	function toggleDetails(e: Event) {
		e.stopPropagation();
		detailsExpanded = !detailsExpanded;
	}

	$: mapUrl = getMapUrl(photo);
	$: imageHeight = variant === 'card' ? '200px' : '150px';
	$: hasDetails = (showDates && photo.uploaded_at) || (photo.latitude && photo.longitude) || $$slots.details || $app.debug_enabled;
</script>

<div
	class="photo-item {variant}"
	data-testid="photo-item"
	data-filename={photo.original_filename}
>
	<a
		class="photo-image"
		class:clickable={mapUrl}
		style="--image-height: {imageHeight}"
		href={mapUrl || '#'}
		on:click={handleImageClick}
	>
		<img
			src={getPhotoUrl(photo)}
			alt={photo.original_filename}
			loading="lazy"
			data-testid="photo-thumbnail"
		/>
		{#if photo.processing_status !== 'completed'}
			<div class="processing-badge">
				{#if photo.processing_status === 'error'}
					error
				{:else}
					processing
				{/if}
			</div>
		{/if}
	</a>

	<div class="photo-info">
		<h3 class="filename">{photo.original_filename}</h3>

		{#if showDescription && photo.description}
			<p class="description">{photo.description}</p>
		{/if}

		{#if hasDetails || (showDates && photo.captured_at)}
			<div class="captured-row">
				{#if showDates && photo.captured_at}
					<span class="captured-date">{formatDateTime(photo.captured_at)}</span>
				{:else}
					<span></span>
				{/if}
				{#if hasDetails}
					<button
						class="details-toggle"
						class:expanded={detailsExpanded}
						on:click={toggleDetails}
						data-testid="photo-item-details-toggle"
						aria-label="Toggle details"
					>
						<ChevronDown size={14} />
					</button>
				{/if}
			</div>
		{/if}

		{#if detailsExpanded && hasDetails}
			<div class="details-content" data-testid="photo-item-details">
				{#if showDates && photo.uploaded_at}
					<p class="detail-row">Uploaded: {formatDateTime(photo.uploaded_at)}</p>
				{/if}

				{#if photo.latitude && photo.longitude}
					<p class="detail-row location">
						<span class="location-icon">📍</span>
						{photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}
					</p>
				{/if}

				<slot name="details"></slot>

				{#if $app.debug_enabled}
					<details class="debug-details">
						<summary>[debug]</summary>
						<pre>{JSON.stringify(photo, null, 2)}</pre>
					</details>
				{/if}
			</div>
		{/if}

		<slot name="actions"></slot>


	</div>
</div>

<style>
	.photo-item {
		border: 1px solid #eee;
		border-radius: 8px;
		overflow: hidden;
		background: white;
		transition: transform 0.2s ease, box-shadow 0.2s ease;
	}

	.photo-item:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
	}

	/* Thumbnail variant (activity page) */
	.photo-item.thumbnail {
		border: 1px solid #dee2e6;
		border-radius: 6px;
		background: #f8f9fa;
	}

	.photo-image {
		display: block;
		position: relative;
		height: var(--image-height);
		overflow: hidden;
		background: #f8f9fa;
		text-decoration: none;
	}

	.photo-image.clickable {
		cursor: pointer;
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

	/* Thumbnail variant has less padding */
	.photo-item.thumbnail .photo-info {
		padding: 12px;
	}

	.filename {
		margin: 0 0 8px 0;
		font-size: 1rem;
		font-weight: 600;
		color: #333;
		word-break: break-word;
	}

	/* Thumbnail variant has smaller filename */
	.photo-item.thumbnail .filename {
		font-size: 0.9rem;
		font-weight: 500;
		margin: 0 0 4px 0;
	}

	.time {
		margin: 0 0 4px 0;
		font-size: 0.9rem;
		color: #6c757d;
	}

	.description {
		margin: 8px 0 0 0;
		font-size: 0.9rem;
		color: #555;
		font-style: italic;
	}

	.photo-info p {
		margin: 0 0 0.25rem 0;
	}

	.photo-info p:last-child {
		margin-bottom: 0;
	}

	/* Captured row with inline chevron */
	.captured-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-top: 4px;
	}

	.captured-date {
		font-size: 0.85rem;
		color: #666;
	}

	.photo-item.thumbnail .captured-date {
		font-size: 0.8rem;
	}

	/* Details toggle button */
	.details-toggle {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 2px;
		background: transparent;
		border: none;
		border-radius: 3px;
		color: #999;
		cursor: pointer;
		transition: color 0.2s, background-color 0.2s;
	}

	.details-toggle:hover {
		background: #f0f0f0;
		color: #666;
	}

	.details-toggle :global(svg) {
		transition: transform 0.2s ease;
	}

	.details-toggle.expanded :global(svg) {
		transform: rotate(180deg);
	}

	/* Details content */
	.details-content {
		margin-top: 8px;
		padding-top: 8px;
		border-top: 1px solid #eee;
	}

	.detail-row {
		margin: 0 0 4px 0;
		font-size: 0.8rem;
		color: #666;
	}

	.detail-row.location {
		color: #28a745;
		display: flex;
		align-items: center;
		gap: 2px;
	}

	.location-icon {
		font-size: 0.9rem;
	}

	/* Thumbnail variant details */
	.photo-item.thumbnail .details-toggle {
		font-size: 0.75rem;
		padding: 2px 6px;
	}

	.photo-item.thumbnail .detail-row {
		font-size: 0.75rem;
	}

	/* Debug details */
	.debug-details {
		margin-top: 8px;
		font-size: 0.75rem;
	}

	.debug-details summary {
		cursor: pointer;
		color: #888;
	}

	.debug-details pre {
		margin: 4px 0 0 0;
		padding: 8px;
		background: #f5f5f5;
		border-radius: 4px;
		overflow-x: auto;
		font-size: 0.7rem;
		max-height: 200px;
		overflow-y: auto;
	}
</style>
