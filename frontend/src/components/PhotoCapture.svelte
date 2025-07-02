<script lang="ts">
	import { onMount } from 'svelte';
	import { geolocation, type GeolocationPosition } from '$lib/geolocation';
	import { photoCaptureService, type CapturedPhotoData } from '$lib/photoCapture';
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	let fileInput: HTMLInputElement;
	let capturing = false;
	let locationError: string | null = null;
	let currentLocation: GeolocationPosition | null = null;
	let previewUrl: string | null = null;

	async function getLocationData(): Promise<GeolocationPosition> {
		return new Promise((resolve, reject) => {
			geolocation.getCurrentPosition(
				(position) => {
					currentLocation = position;
					locationError = null;
					resolve(position);
				},
				(error) => {
					locationError = error.message;
					reject(error);
				},
				{
					enableHighAccuracy: true,
					timeout: 10000,
					maximumAge: 0
				}
			);
		});
	}

	async function capturePhoto() {
		capturing = true;
		locationError = null;

		try {
			// Get location first
			const location = await getLocationData();
			
			// Trigger file input
			fileInput.click();
		} catch (error) {
			capturing = false;
			console.error('Failed to get location:', error);
		}
	}

	async function handleFileSelect(event: Event) {
		const target = event.target as HTMLInputElement;
		const file = target.files?.[0];

		if (!file || !currentLocation) {
			capturing = false;
			return;
		}

		// Create preview
		previewUrl = URL.createObjectURL(file);

		const capturedPhoto: CapturedPhotoData = {
			image: file,
			location: {
				latitude: currentLocation.coords.latitude,
				longitude: currentLocation.coords.longitude,
				altitude: currentLocation.coords.altitude,
				accuracy: currentLocation.coords.accuracy
			},
			bearing: currentLocation.coords.heading,
			timestamp: currentLocation.timestamp
		};

		try {
			// Save photo with embedded EXIF metadata
			const devicePhoto = await photoCaptureService.savePhotoWithExif(capturedPhoto);
			dispatch('photoCaptured', { ...capturedPhoto, savedPath: devicePhoto.path, devicePhoto });
		} catch (error) {
			console.error('Failed to save photo:', error);
			locationError = 'Failed to save photo with metadata';
		}

		capturing = false;

		// Reset file input for next capture
		fileInput.value = '';
	}

	onMount(() => {
		return () => {
			if (previewUrl) {
				URL.revokeObjectURL(previewUrl);
			}
		};
	});
</script>

<div class="photo-capture" data-testid="photo-capture">
	<input
		bind:this={fileInput}
		type="file"
		accept="image/*"
		capture="environment"
		on:change={handleFileSelect}
		style="display: none;"
		data-testid="photo-input"
	/>

	<button
		on:click={capturePhoto}
		disabled={capturing}
		class="capture-button"
		data-testid="capture-button"
	>
		{#if capturing}
			<span class="spinner"></span>
			Getting location...
		{:else}
			📸 Take Photo
		{/if}
	</button>

	{#if locationError}
		<div class="error" data-testid="location-error">
			⚠️ Location error: {locationError}
		</div>
	{/if}

	{#if currentLocation && !capturing}
		<div class="location-info" data-testid="location-info">
			<div>📍 Lat: {currentLocation.coords.latitude.toFixed(6)}</div>
			<div>📍 Lng: {currentLocation.coords.longitude.toFixed(6)}</div>
			{#if currentLocation.coords.heading !== null}
				<div>🧭 Bearing: {currentLocation.coords.heading.toFixed(1)}°</div>
			{/if}
			{#if currentLocation.coords.altitude !== null}
				<div>⛰️ Alt: {currentLocation.coords.altitude.toFixed(1)}m</div>
			{/if}
			<div>🎯 Accuracy: ±{currentLocation.coords.accuracy.toFixed(1)}m</div>
		</div>
	{/if}

	{#if previewUrl}
		<div class="preview" data-testid="photo-preview">
			<img src={previewUrl} alt="Preview of capture" />
		</div>
	{/if}
</div>

<style>
	.photo-capture {
		display: flex;
		flex-direction: column;
		gap: 1rem;
		padding: 1rem;
		background: var(--background-color, #fff);
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.capture-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 0.75rem 1.5rem;
		font-size: 1rem;
		background: #007bff;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		transition: background 0.2s;
	}

	.capture-button:hover:not(:disabled) {
		background: #0056b3;
	}

	.capture-button:disabled {
		background: #6c757d;
		cursor: not-allowed;
	}

	.spinner {
		display: inline-block;
		width: 1rem;
		height: 1rem;
		border: 2px solid #f3f3f3;
		border-top: 2px solid #333;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}

	.error {
		padding: 0.5rem;
		background: #fee;
		color: #c00;
		border-radius: 4px;
		font-size: 0.9rem;
	}

	.location-info {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: 0.5rem;
		padding: 0.75rem;
		background: #f8f9fa;
		border-radius: 4px;
		font-size: 0.9rem;
		font-family: monospace;
	}

	.preview {
		max-width: 300px;
		margin: 0 auto;
	}

	.preview img {
		width: 100%;
		height: auto;
		border-radius: 4px;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
	}
</style>