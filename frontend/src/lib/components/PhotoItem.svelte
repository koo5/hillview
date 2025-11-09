<script lang="ts">
	import { myGoto } from '$lib/navigation.svelte';
	import { constructPhotoMapUrl } from '$lib/urlUtils';
	import { app } from '$lib/data.svelte';
	import { zoomViewData } from '$lib/zoomView.svelte';
	import { doubleTap } from '$lib/actions/doubleTap';
	import { getFullPhotoInfo } from '$lib/photoUtils';
	import type { PhotoItemData } from '$lib/types/photoItemTypes';

	// Props
	export let photo: PhotoItemData;
	export let variant: 'card' | 'thumbnail' = 'card'; // 'card' for users page, 'thumbnail' for activity
	export let showDates = true;
	export let showTime = false;
	export let showDescription = true;

	// Helper functions
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

	function getPhotoUrl(photo: PhotoItemData): string {
		return photo.sizes?.['320']?.url || '';
	}

	function viewOnMap(photo: PhotoItemData) {
		if (photo.latitude && photo.longitude) {
			// Navigate to main page with photo coordinates and switch to gallery view
			myGoto(constructPhotoMapUrl(photo));
			// Set activity to 'view' to show gallery
			app.update(a => ({ ...a, activity: 'view' }));
		}
	}

	function openZoomView(photo: PhotoItemData) {
		const fallbackUrl = getPhotoUrl(photo);
		const fullPhotoInfo = getFullPhotoInfo(photo);

		zoomViewData.set({
			fallback_url: fallbackUrl,
			url: fullPhotoInfo.url,
			filename: photo.original_filename,
			width: fullPhotoInfo.width,
			height: fullPhotoInfo.height
		});
	}

	$: isClickable = photo.latitude && photo.longitude;
	$: imageHeight = variant === 'card' ? '200px' : '150px';
</script>

<div
	class="photo-item {variant}"
	class:clickable={isClickable}
	on:click={() => viewOnMap(photo)}
	on:keydown={(e) => e.key === 'Enter' && viewOnMap(photo)}
	role="button"
	tabindex={isClickable ? 0 : -1}
>
	<div class="photo-image" style="--image-height: {imageHeight}">
		<img
			src={getPhotoUrl(photo)}
			alt={photo.original_filename}
			loading="lazy"
			use:doubleTap={() => openZoomView(photo)}
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
	</div>

	<div class="photo-info">
		<h3 class="filename">{photo.original_filename}</h3>

		{#if showDates}
			<p class="date">Uploaded: {formatDate(photo.uploaded_at)}</p>
			{#if photo.captured_at}
				<p class="date">Captured: {formatDate(photo.captured_at)}</p>
			{/if}
		{/if}

		{#if showTime}
			<p class="time">{formatTime(photo.uploaded_at)}</p>
		{/if}

		{#if photo.latitude && photo.longitude}
			<p class="location">📍 {photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}</p>
		{/if}

		{#if showDescription && photo.description}
			<p class="description">{photo.description}</p>
		{/if}
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

	.photo-item.clickable {
		cursor: pointer;
	}

	.photo-item.clickable:hover {
		transform: translateY(-4px);
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
	}

	/* Thumbnail variant (activity page) */
	.photo-item.thumbnail {
		border: 1px solid #dee2e6;
		border-radius: 6px;
		background: #f8f9fa;
	}

	.photo-image {
		position: relative;
		height: var(--image-height);
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

	.date {
		margin: 0 0 4px 0;
		font-size: 0.85rem;
		color: #666;
	}

	.time {
		margin: 0 0 4px 0;
		font-size: 0.9rem;
		color: #6c757d;
	}

	.location {
		margin: 4px 0;
		font-size: 0.85rem;
		color: #28a745;
	}

	/* Thumbnail variant has smaller location text */
	.photo-item.thumbnail .location {
		font-size: 0.8rem;
		margin: 0 0 4px 0;
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
</style>
