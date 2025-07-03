<script lang="ts">
	import { onMount } from 'svelte';
	import { geolocation, type GeolocationPosition } from '$lib/geolocation';
	import { photoCaptureService, type CapturedPhotoData } from '$lib/photoCapture';
	import { createEventDispatcher } from 'svelte';

	const dispatch = createEventDispatcher();

	export let autoCapture = false; // Allow auto-opening camera when ready

	let fileInput: HTMLInputElement;
	let capturing = false;
	let initializingLocation = false;
	let locationReady = false;
	let locationError: string | null = null;
	let currentLocation: GeolocationPosition | null = null;
	let previewUrl: string | null = null;
	let watchId: number | null = null;

	async function getLocationData(): Promise<GeolocationPosition> {
		return new Promise((resolve, reject) => {
			geolocation.getCurrentPosition(
				(position) => {
					currentLocation = position;
					locationError = null;
					locationReady = true;
					resolve(position);
				},
				(error) => {
					locationError = error.message;
					locationReady = false;
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

	async function startLocationWatch() {
		// Watch position for continuous updates
		watchId = geolocation.watchPosition(
			(position) => {
				currentLocation = position;
				locationError = null;
				locationReady = true;
			},
			(error) => {
				locationError = error.message;
				locationReady = false;
			},
			{
				enableHighAccuracy: true,
				timeout: 5000,
				maximumAge: 0
			}
		);
	}

	async function initializeLocation() {
		initializingLocation = true;
		try {
			await getLocationData();
			startLocationWatch();
			
			// If autoCapture is enabled and location is ready, open camera
			if (autoCapture && locationReady && fileInput) {
				setTimeout(() => {
					fileInput.click();
				}, 500); // Small delay to ensure UI is ready
			}
		} catch (error) {
			console.error('Failed to initialize location:', error);
		} finally {
			initializingLocation = false;
		}
	}

	async function capturePhoto() {
		if (!locationReady) {
			capturing = true;
			locationError = null;

			try {
				// Try to get fresh location
				await getLocationData();
			} catch (error) {
				capturing = false;
				console.error('Failed to get location:', error);
				return;
			}
		}

		// Trigger file input
		fileInput.click();
		capturing = false;
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
		// Initialize location immediately when component mounts
		initializeLocation();

		return () => {
			// Cleanup
			if (previewUrl) {
				URL.revokeObjectURL(previewUrl);
			}
			if (watchId !== null) {
				geolocation.clearWatch(watchId);
			}
		};
	});
</script>

<div class="photo-capture" data-testid="photo-capture">
	<input
		bind:this={fileInput}
		type="file"
		accept="image/*"
		capture="camera"
		on:change={handleFileSelect}
		style="display: none;"
		data-testid="photo-input"
	/>

	<button
		on:click={capturePhoto}
		disabled={capturing || initializingLocation || (!locationReady && !currentLocation)}
		class="capture-button {locationReady ? 'ready' : ''}"
		data-testid="capture-button"
	>
		{#if initializingLocation}
			<span class="spinner"></span>
			Getting location...
		{:else if capturing}
			<span class="spinner"></span>
			Opening camera...
		{:else if locationReady}
			📸 Take Photo
		{:else if locationError}
			⚠️ Enable Location
		{:else}
			📍 Waiting for location...
		{/if}
	</button>

	{#if locationError}
		<div class="error" data-testid="location-error">
			<div class="error-content">
				<span>⚠️ Location error: {locationError}</span>
				{#if locationError.includes('denied') || locationError.includes('permission')}
					<button class="retry-button" on:click={initializeLocation}>
						🔄 Retry
					</button>
				{/if}
			</div>
			{#if locationError.includes('denied')}
				<div class="permission-help">
					Please enable location permissions in your device settings to use this feature.
				</div>
			{/if}
		</div>
	{/if}

	{#if currentLocation}
		<div class="location-info {locationReady ? 'active' : ''}" data-testid="location-info">
			<div>📍 Lat: {currentLocation.coords.latitude.toFixed(6)}</div>
			<div>📍 Lng: {currentLocation.coords.longitude.toFixed(6)}</div>
			{#if currentLocation.coords.heading !== null}
				<div>🧭 Bearing: {currentLocation.coords.heading.toFixed(1)}°</div>
			{/if}
			{#if currentLocation.coords.altitude !== null}
				<div>⛰️ Alt: {currentLocation.coords.altitude.toFixed(1)}m</div>
			{/if}
			<div>🎯 Accuracy: ±{currentLocation.coords.accuracy.toFixed(1)}m</div>
			{#if watchId !== null}
				<div class="live-indicator">🔴 Live</div>
			{/if}
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

	.capture-button.ready {
		background: #28a745;
		animation: pulse 2s infinite;
	}

	.capture-button.ready:hover {
		background: #218838;
	}

	@keyframes pulse {
		0% {
			box-shadow: 0 0 0 0 rgba(40, 167, 69, 0.4);
		}
		70% {
			box-shadow: 0 0 0 10px rgba(40, 167, 69, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(40, 167, 69, 0);
		}
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
		padding: 0.75rem;
		background: #fee;
		color: #c00;
		border-radius: 4px;
		font-size: 0.9rem;
		border: 1px solid #fcc;
	}

	.error-content {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
	}

	.retry-button {
		padding: 0.25rem 0.75rem;
		background: white;
		color: #c00;
		border: 1px solid #c00;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.85rem;
		transition: all 0.2s;
	}

	.retry-button:hover {
		background: #c00;
		color: white;
	}

	.permission-help {
		margin-top: 0.5rem;
		font-size: 0.85rem;
		color: #800;
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
		border: 2px solid transparent;
		transition: all 0.3s;
		position: relative;
	}

	.location-info.active {
		background: #e8f5e9;
		border-color: #4caf50;
	}

	.live-indicator {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		font-size: 0.8rem;
		animation: blink 1.5s infinite;
	}

	@keyframes blink {
		0%, 50% { opacity: 1; }
		51%, 100% { opacity: 0.3; }
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