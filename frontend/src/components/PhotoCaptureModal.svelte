<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { geolocation, type GeolocationPosition } from '$lib/geolocation';
	import { photoCaptureService, type CapturedPhotoData } from '$lib/photoCapture';
	import { createEventDispatcher } from 'svelte';
	import { X } from 'lucide-svelte';
	import { getBuildInfo } from '$lib/build-info';

	const dispatch = createEventDispatcher();
	const buildInfo = getBuildInfo();

	export let show = false;

	let fileInput: HTMLInputElement;
	let locationReady = false;
	let locationError: string | null = null;
	let currentLocation: GeolocationPosition | null = null;
	let watchId: number | null = null;
	let capturedPhotos: Array<{ url: string; data: CapturedPhotoData; devicePhoto?: any }> = [];

	// Start location acquisition immediately
	async function initializeLocation() {
		try {
			// Get initial position with a shorter timeout
			await new Promise<void>((resolve, reject) => {
				const timeoutId = setTimeout(() => {
					locationError = 'Location timeout - camera will open anyway';
					resolve();
				}, 3000); // 3 second timeout
				
				geolocation.getCurrentPosition(
					(position) => {
						clearTimeout(timeoutId);
						currentLocation = position;
						locationError = null;
						locationReady = true;
						resolve();
					},
					(error) => {
						clearTimeout(timeoutId);
						locationError = error.message;
						locationReady = false;
						// Don't reject - we'll still open camera
						resolve();
					},
					{
						enableHighAccuracy: true,
						timeout: 3000, // Reduced from 10000
						maximumAge: 0
					}
				);
			});

			// Start watching position with frequent updates for bearing
			watchId = geolocation.watchPosition(
				(position) => {
					currentLocation = position;
					locationError = null;
					locationReady = true;
				},
				(error) => {
					locationError = error.message;
					// Don't set locationReady to false if we already have a position
					if (!currentLocation) {
						locationReady = false;
					}
				},
				{
					enableHighAccuracy: true,
					timeout: 5000,
					maximumAge: 0  // Always get fresh location
				}
			);
		} catch (error) {
			console.error('Failed to initialize location:', error);
		}
	}

	function openCamera() {
		if (fileInput) {
			fileInput.click();
		}
	}

	async function handleFileSelect(event: Event) {
		const target = event.target as HTMLInputElement;
		const file = target.files?.[0];

		if (!file) {
			return;
		}

		// Create preview
		const previewUrl = URL.createObjectURL(file);

		// If no location yet, wait a bit more
		if (!currentLocation) {
			locationError = 'Waiting for location...';
			// Try one more time
			await new Promise<void>((resolve) => {
				geolocation.getCurrentPosition(
					(position) => {
						currentLocation = position;
						locationError = null;
						locationReady = true;
						resolve();
					},
					() => {
						// Continue without location
						resolve();
					},
					{
						enableHighAccuracy: true,
						timeout: 5000,
						maximumAge: 0
					}
				);
			});
		}

		if (currentLocation) {
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
				capturedPhotos = [...capturedPhotos, { url: previewUrl, data: capturedPhoto, devicePhoto }];
				dispatch('photoCaptured', { ...capturedPhoto, savedPath: devicePhoto.path, devicePhoto });
			} catch (error) {
				console.error('Failed to save photo:', error);
				locationError = 'Failed to save photo with metadata';
			}
		} else {
			locationError = 'No location available. Photo saved without location data.';
			// Still save the photo without location
			capturedPhotos = [...capturedPhotos, { 
				url: previewUrl, 
				data: {
					image: file,
					location: null,
					bearing: null,
					timestamp: Date.now()
				} as any 
			}];
		}

		// Reset file input for next capture
		fileInput.value = '';
	}

	function close() {
		show = false;
		dispatch('close');
	}

	function getCompassDirection(heading: number): string {
		const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
		const index = Math.round(heading / 45) % 8;
		return directions[index];
	}

	// When modal opens, initialize location and open camera
	$: if (show) {
		capturedPhotos = [];
		initializeLocation().then(() => {
			// Open camera immediately after modal opens
			setTimeout(() => {
				openCamera();
			}, 100);
		});
	}

	onDestroy(() => {
		// Cleanup
		if (watchId !== null) {
			geolocation.clearWatch(watchId);
		}
		capturedPhotos.forEach(photo => {
			URL.revokeObjectURL(photo.url);
		});
	});
</script>

{#if show}
	<div class="modal-backdrop" on:click={close} on:keydown={(e) => e.key === 'Escape' && close()} role="presentation">
		<div class="modal-content" on:click|stopPropagation on:keydown={() => {}} role="dialog" aria-modal="true" tabindex="-1">
			<div class="modal-header">
				<h2>Take Photo</h2>
				<div class="build-info">
					<small>Build: {new Date(buildInfo.buildTime).toLocaleString()}</small>
				</div>
				<button class="close-button" on:click={close} aria-label="Close">
					<X size={24} />
				</button>
			</div>

			<input
				bind:this={fileInput}
				type="file"
				accept="image/*"
				capture="camera"
				on:change={handleFileSelect}
				style="display: none;"
				data-testid="photo-input"
			/>

			<div class="modal-body">
				<!-- Live location overlay -->
				<div class="location-overlay {locationReady ? 'ready' : ''} {locationError ? 'error' : ''}">
					{#if locationError}
						<div class="location-row">
							<span class="icon">⚠️</span>
							<span>{locationError}</span>
						</div>
					{:else if currentLocation}
						<div class="location-row">
							<span class="icon">📍</span>
							<span>{currentLocation.coords.latitude.toFixed(6)}°, {currentLocation.coords.longitude.toFixed(6)}°</span>
						</div>
						{#if currentLocation.coords.heading !== null && currentLocation.coords.heading !== undefined}
							<div class="location-row">
								<span class="icon">🧭</span>
								<span>{currentLocation.coords.heading.toFixed(1)}° ({getCompassDirection(currentLocation.coords.heading)})</span>
							</div>
						{/if}
						{#if currentLocation.coords.altitude !== null && currentLocation.coords.altitude !== undefined}
							<div class="location-row">
								<span class="icon">⛰️</span>
								<span>{currentLocation.coords.altitude.toFixed(1)}m altitude</span>
							</div>
						{/if}
						<div class="location-row">
							<span class="icon">🎯</span>
							<span>±{currentLocation.coords.accuracy.toFixed(0)}m accuracy</span>
						</div>
					{:else}
						<div class="location-row">
							<span class="spinner"></span>
							<span>Getting location...</span>
						</div>
					{/if}
					{#if watchId !== null && locationReady}
						<div class="live-indicator">● LIVE</div>
					{/if}
				</div>

				<button
					on:click={openCamera}
					class="camera-button"
					data-testid="camera-button"
				>
					📸 {capturedPhotos.length > 0 ? 'Take Another Photo' : 'Take Photo'}
				</button>

				{#if capturedPhotos.length > 0}
					<div class="captured-photos">
						<h3>Captured Photos ({capturedPhotos.length})</h3>
						<div class="photo-grid">
							{#each capturedPhotos as photo}
								<div class="photo-thumbnail">
									<img src={photo.url} alt="Captured" />
									{#if photo.data.location}
										<div class="photo-info">
											📍 {photo.data.location.latitude.toFixed(4)}, {photo.data.location.longitude.toFixed(4)}
										</div>
									{:else}
										<div class="photo-info no-location">
											📍 No location
										</div>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.modal-backdrop {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.5);
		z-index: 40000;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.modal-content {
		background: white;
		border-radius: 8px;
		width: 100%;
		max-width: 600px;
		max-height: 90vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem 1.5rem;
		border-bottom: 1px solid #eee;
	}

	.modal-header h2 {
		margin: 0;
		font-size: 1.5rem;
		color: #333;
	}
	
	.build-info {
		flex: 1;
		text-align: center;
		color: #666;
		font-size: 0.75rem;
		opacity: 0.7;
	}

	.close-button {
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.5rem;
		border-radius: 4px;
		transition: background 0.2s;
	}

	.close-button:hover {
		background: #f0f0f0;
	}

	.modal-body {
		padding: 1.5rem;
		overflow-y: auto;
		flex: 1;
	}

	.location-overlay {
		background: rgba(0, 0, 0, 0.8);
		color: white;
		padding: 1rem;
		border-radius: 8px;
		margin-bottom: 1.5rem;
		position: relative;
		font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
		font-size: 0.9rem;
		border: 2px solid rgba(255, 255, 255, 0.2);
		backdrop-filter: blur(10px);
	}

	.location-overlay.ready {
		border-color: #4caf50;
		background: rgba(76, 175, 80, 0.1);
	}

	.location-overlay.error {
		border-color: #f44336;
		background: rgba(244, 67, 54, 0.1);
	}

	.location-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin: 0.5rem 0;
	}

	.location-row .icon {
		font-size: 1.2rem;
		width: 1.5rem;
		text-align: center;
	}

	.live-indicator {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		font-size: 0.75rem;
		color: #4caf50;
		font-weight: bold;
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.3; }
	}

	.camera-button {
		width: 100%;
		padding: 1rem;
		font-size: 1.1rem;
		background: #4a90e2;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		transition: background 0.2s;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
	}

	.camera-button:hover {
		background: #3a7bc8;
	}

	.spinner {
		display: inline-block;
		width: 1rem;
		height: 1rem;
		border: 2px solid #ccc;
		border-top: 2px solid #666;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}

	.captured-photos {
		margin-top: 2rem;
		padding-top: 2rem;
		border-top: 1px solid #eee;
	}

	.captured-photos h3 {
		margin: 0 0 1rem 0;
		color: #555;
		font-size: 1.1rem;
	}

	.photo-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 1rem;
	}

	.photo-thumbnail {
		position: relative;
		border-radius: 6px;
		overflow: hidden;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
	}

	.photo-thumbnail img {
		width: 100%;
		height: 150px;
		object-fit: cover;
	}

	.photo-info {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.photo-info.no-location {
		background: rgba(200, 0, 0, 0.7);
	}

	@media (max-width: 600px) {
		.modal-content {
			max-height: 100vh;
			margin: 0;
			border-radius: 0;
		}

		.photo-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>