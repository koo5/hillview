<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { createEventDispatcher } from 'svelte';
	import { Camera, X } from 'lucide-svelte';
	
	const dispatch = createEventDispatcher();
	
	export let show = false;
	export let locationData: {
		latitude?: number;
		longitude?: number;
		altitude?: number | null;
		accuracy?: number;
		heading?: number | null;
	} | null = null;
	export let locationError: string | null = null;
	export let locationReady = false;
	
	let video: HTMLVideoElement;
	let canvas: HTMLCanvasElement;
	let stream: MediaStream | null = null;
	let facing: 'user' | 'environment' = 'environment';
	let cameraReady = false;
	let cameraError: string | null = null;
	let zoomSupported = false;
	let zoomLevel = 1;
	let minZoom = 1;
	let maxZoom = 1;
	let videoTrack: MediaStreamTrack | null = null;
	
	async function startCamera() {
		try {
			// Check for camera support
			if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
				throw new Error('Camera API not supported');
			}
			
			// Stop any existing stream
			if (stream) {
				stream.getTracks().forEach(track => track.stop());
			}
			
			
			// Request camera access
			const constraints: MediaStreamConstraints = {
				video: {
					facingMode: facing,
					width: { ideal: 1920 },
					height: { ideal: 1080 }
				}
			};
			stream = await navigator.mediaDevices.getUserMedia(constraints);
			
			if (video) {
				video.srcObject = stream;
				await video.play();
				cameraReady = true;
				cameraError = null;
				
				// Check zoom support
				videoTrack = stream.getVideoTracks()[0];
				if (videoTrack) {
					const capabilities = videoTrack.getCapabilities() as any;
					if ('zoom' in capabilities && capabilities.zoom) {
						zoomSupported = true;
						minZoom = capabilities.zoom.min || 1;
						maxZoom = capabilities.zoom.max || 1;
						const settings = videoTrack.getSettings() as any;
						zoomLevel = settings.zoom || 1;
					}
				}
			}
		} catch (error) {
			console.error('Camera error:', error);
			cameraError = error instanceof Error ? error.message : 'Failed to access camera';
			cameraReady = false;
		}
	}
	
	
	async function setZoom(level: number) {
		if (!videoTrack || !zoomSupported) return;
		
		try {
			await videoTrack.applyConstraints({
				advanced: [{ zoom: level } as any]
			} as MediaTrackConstraints);
			zoomLevel = level;
		} catch (error) {
			console.error('Failed to set zoom:', error);
		}
	}
	
	function handleZoomChange(event: Event) {
		const target = event.target as HTMLInputElement;
		setZoom(parseFloat(target.value));
	}
	
	function capturePhoto() {
		if (!video || !canvas || !cameraReady) return;
		
		const context = canvas.getContext('2d');
		if (!context) return;
		
		// Set canvas size to match video
		canvas.width = video.videoWidth;
		canvas.height = video.videoHeight;
		
		// Draw video frame to canvas
		context.drawImage(video, 0, 0);
		
		// Convert canvas to blob
		canvas.toBlob((blob) => {
			if (blob) {
				// Create a File object from the blob
				const file = new File([blob], `photo_${Date.now()}.jpg`, { type: 'image/jpeg' });
				dispatch('photoCaptured', { file });
			}
		}, 'image/jpeg', 0.9);
	}
	
	function close() {
		if (stream) {
			stream.getTracks().forEach(track => track.stop());
			stream = null;
		}
		cameraReady = false;
		cameraError = null;
		show = false;
		dispatch('close');
	}
	
	// Start camera when modal opens
	$: if (show && !stream) {
		startCamera();
	} else if (!show && stream) {
		// Stop camera when modal closes
		stream.getTracks().forEach(track => track.stop());
		stream = null;
		cameraReady = false;
	}
	
	onDestroy(() => {
		if (stream) {
			stream.getTracks().forEach(track => track.stop());
		}
	});
</script>

{#if show}
	<div class="camera-container">
		<div class="camera-content">
			<div class="camera-header">
				<h2>Take Photo</h2>
				<button class="close-button" on:click={close} aria-label="Close">
					<X size={24} />
				</button>
			</div>
			
			<div class="camera-view">
				{#if cameraError}
					<div class="camera-error">
						<p>⚠️ {cameraError}</p>
						<button class="retry-button" on:click={startCamera}>
							Try Again
						</button>
					</div>
				{:else}
					<video bind:this={video} class="camera-video" playsinline>
						<track kind="captions" />
					</video>
					<canvas bind:this={canvas} style="display: none;"></canvas>
					
					<!-- Location overlay -->
					<div class="location-overlay {locationReady ? 'ready' : ''} {locationError ? 'error' : ''}">
						{#if locationError}
							<div class="location-row">
								<span class="icon">⚠️</span>
								<span>{locationError}</span>
							</div>
						{:else if locationData}
							<div class="location-row">
								<span class="icon">📍</span>
								<span>{locationData.latitude?.toFixed(6)}°, {locationData.longitude?.toFixed(6)}°</span>
							</div>
							{#if locationData.heading !== null && locationData.heading !== undefined}
								<div class="location-row">
									<span class="icon">🧭</span>
									<span>{locationData.heading.toFixed(1)}°</span>
								</div>
							{/if}
							{#if locationData.altitude !== null && locationData.altitude !== undefined}
								<div class="location-row">
									<span class="icon">⛰️</span>
									<span>{locationData.altitude.toFixed(1)}m</span>
								</div>
							{/if}
							{#if locationData.accuracy}
								<div class="location-row">
									<span class="icon">🎯</span>
									<span>±{locationData.accuracy.toFixed(0)}m</span>
								</div>
							{/if}
						{:else}
							<div class="location-row">
								<span class="spinner"></span>
								<span>Getting location...</span>
							</div>
						{/if}
					</div>
				{/if}
			</div>
			
			{#if zoomSupported && cameraReady}
				<div class="zoom-control">
					<label for="zoom-slider" class="zoom-label">
						{zoomLevel.toFixed(1)}x
					</label>
					<input
						id="zoom-slider"
						type="range"
						min={minZoom}
						max={maxZoom}
						step="0.1"
						value={zoomLevel}
						on:input={handleZoomChange}
						class="zoom-slider"
						aria-label="Camera zoom"
					/>
				</div>
			{/if}
			
			<div class="camera-controls">
				<button 
					class="capture-button" 
					on:click={capturePhoto}
					disabled={!cameraReady}
					aria-label="Capture photo"
				>
					<Camera size={32} />
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.camera-container {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		background: black;
	}
	
	.camera-content {
		background: black;
		width: 100%;
		height: 100%;
		max-width: 100vw;
		max-height: 100vh;
		display: flex;
		flex-direction: column;
		position: relative;
	}
	
	.camera-header {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 1rem;
		background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent);
		z-index: 10;
	}
	
	.camera-header h2 {
		margin: 0;
		color: white;
		font-size: 1.25rem;
	}
	
	.close-button {
		background: rgba(255, 255, 255, 0.2);
		border: none;
		color: white;
		cursor: pointer;
		padding: 0.5rem;
		border-radius: 50%;
		transition: background 0.2s;
	}
	
	.close-button:hover {
		background: rgba(255, 255, 255, 0.3);
	}
	
	.camera-view {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		overflow: hidden;
	}
	
	.camera-video {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	
	.camera-error {
		text-align: center;
		color: white;
		padding: 2rem;
	}
	
	.camera-error p {
		margin-bottom: 1rem;
		font-size: 1.1rem;
	}
	
	.retry-button {
		padding: 0.75rem 1.5rem;
		background: #4a90e2;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 1rem;
		transition: background 0.2s;
	}
	
	.retry-button:hover {
		background: #3a7bc8;
	}
	
	.camera-controls {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		display: flex;
		justify-content: center;
		align-items: center;
		gap: 2rem;
		padding: 2rem;
		background: linear-gradient(to top, rgba(0,0,0,0.8), transparent);
	}
	
	.capture-button {
		width: 72px;
		height: 72px;
		border-radius: 50%;
		background: white;
		border: 4px solid rgba(255, 255, 255, 0.3);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.2s;
		color: black;
	}
	
	.capture-button:hover:not(:disabled) {
		transform: scale(1.1);
		border-color: rgba(255, 255, 255, 0.5);
	}
	
	.capture-button:active:not(:disabled) {
		transform: scale(0.95);
	}
	
	.capture-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	
	.location-overlay {
		position: absolute;
		top: 80px;
		left: 1rem;
		background: rgba(0, 0, 0, 0.7);
		color: white;
		padding: 0.75rem;
		border-radius: 8px;
		font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
		font-size: 0.85rem;
		border: 2px solid rgba(255, 255, 255, 0.2);
		backdrop-filter: blur(10px);
		max-width: 90%;
	}
	
	.location-overlay.ready {
		border-color: #4caf50;
		background: rgba(76, 175, 80, 0.2);
	}
	
	.location-overlay.error {
		border-color: #f44336;
		background: rgba(244, 67, 54, 0.2);
	}
	
	.location-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0.25rem 0;
		white-space: nowrap;
	}
	
	.location-row .icon {
		font-size: 1rem;
		width: 1.2rem;
		text-align: center;
	}
	
	.spinner {
		display: inline-block;
		width: 0.8rem;
		height: 0.8rem;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top: 2px solid white;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}
	
	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}
	
	.zoom-control {
		position: absolute;
		right: 1rem;
		top: 50%;
		transform: translateY(-50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		padding: 1rem;
		background: rgba(0, 0, 0, 0.6);
		border-radius: 8px;
		backdrop-filter: blur(10px);
	}
	
	.zoom-label {
		color: white;
		font-size: 0.9rem;
		font-weight: 500;
		min-width: 3em;
		text-align: center;
	}
	
	.zoom-slider {
		width: 150px;
		transform: rotate(-90deg);
		transform-origin: center;
		margin: 60px 0;
		cursor: pointer;
	}
	
	.zoom-slider::-webkit-slider-track {
		background: rgba(255, 255, 255, 0.3);
		height: 4px;
		border-radius: 2px;
	}
	
	.zoom-slider::-webkit-slider-thumb {
		-webkit-appearance: none;
		appearance: none;
		width: 16px;
		height: 16px;
		background: white;
		border-radius: 50%;
		cursor: pointer;
	}
	
	.zoom-slider::-moz-range-track {
		background: rgba(255, 255, 255, 0.3);
		height: 4px;
		border-radius: 2px;
	}
	
	.zoom-slider::-moz-range-thumb {
		width: 16px;
		height: 16px;
		background: white;
		border-radius: 50%;
		border: none;
		cursor: pointer;
	}
	
	@media (max-width: 600px) {
		.camera-header h2 {
			font-size: 1rem;
		}
		
		.camera-controls {
			padding: 1rem;
			gap: 1rem;
		}
		
		.capture-button {
			width: 60px;
			height: 60px;
		}
		
		
		.zoom-control {
			right: 0.5rem;
			padding: 0.5rem;
		}
		
		.zoom-slider {
			width: 100px;
			margin: 40px 0;
		}
	}
</style>