<script lang="ts">
	import PhotoCapture from '../../components/PhotoCapture.svelte';
	import type { CapturedPhotoData } from '$lib/photoCapture';
	import { fetch_photos } from '$lib/sources';
	import { goto } from '$app/navigation';
	
	interface CapturedPhotoWithPath extends CapturedPhotoData {
		savedPath: string;
	}
	
	let capturedPhotos: CapturedPhotoWithPath[] = [];
	
	async function handlePhotoCaptured(event: CustomEvent<CapturedPhotoWithPath>) {
		capturedPhotos = [...capturedPhotos, event.detail];
		// Refresh photos to include the new device photo
		await fetch_photos();
	}
	
	function goBack() {
		goto('/');
	}
</script>

<div class="camera-page">
	<div class="header">
		<button class="back-button" on:click={goBack} aria-label="Go back">
			← Back
		</button>
		<h1>📸 Camera</h1>
	</div>
	
	<PhotoCapture on:photoCaptured={handlePhotoCaptured} autoCapture={true} />
	
	{#if capturedPhotos.length > 0}
		<div class="captured-photos">
			<h2>Captured Photos</h2>
			{#each capturedPhotos as photo, index}
				<div class="photo-card" data-testid="captured-photo-{index}">
					<img src={URL.createObjectURL(photo.image)} alt="Captured photo {index + 1}" />
					<div class="photo-info">
						<p><strong>Location:</strong></p>
						<p>Lat: {photo.location.latitude.toFixed(6)}</p>
						<p>Lng: {photo.location.longitude.toFixed(6)}</p>
						{#if photo.bearing !== null && photo.bearing !== undefined}
							<p>Bearing: {photo.bearing.toFixed(1)}°</p>
						{/if}
						{#if photo.location.altitude !== null && photo.location.altitude !== undefined}
							<p>Altitude: {photo.location.altitude.toFixed(1)}m</p>
						{/if}
						<p>Accuracy: ±{photo.location.accuracy.toFixed(1)}m</p>
						<p><small>Saved to: {photo.savedPath}</small></p>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.camera-page {
		max-width: 800px;
		margin: 0 auto;
		padding: 1rem;
	}
	
	.header {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 2rem;
	}
	
	.back-button {
		padding: 0.5rem 1rem;
		background: #f0f0f0;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		font-size: 1rem;
		transition: background 0.2s;
	}
	
	.back-button:hover {
		background: #e0e0e0;
	}
	
	h1 {
		margin: 0;
		flex: 1;
		text-align: center;
	}
	
	.captured-photos {
		margin-top: 2rem;
	}
	
	.photo-card {
		display: grid;
		grid-template-columns: 200px 1fr;
		gap: 1rem;
		margin-bottom: 1.5rem;
		padding: 1rem;
		background: #f5f5f5;
		border-radius: 8px;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
	}
	
	.photo-card img {
		width: 100%;
		height: auto;
		border-radius: 4px;
	}
	
	.photo-info {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}
	
	.photo-info p {
		margin: 0;
		font-family: monospace;
		font-size: 0.9rem;
	}
	
	.photo-info small {
		color: #666;
		word-break: break-all;
	}
</style>