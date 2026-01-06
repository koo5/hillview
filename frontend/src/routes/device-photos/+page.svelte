<script lang="ts">
	import {onMount} from 'svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import {invoke} from "@tauri-apps/api/core";
	import { RefreshCw, Download, Upload, Clock, MapPin, Camera, AlertCircle, ChevronLeft, ChevronRight, CheckCircle } from 'lucide-svelte';
	import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
	import {app} from "$lib/data.svelte";
	import RetryUploadsButton from "$lib/components/RetryUploadsButton.svelte";
	import DevicePhotoStats from "$lib/components/DevicePhotoStats.svelte";
	import {fetchDevicePhotoStats} from "$lib/devicePhotoStats";

	interface DevicePhoto {
		id: string;
		file_path: string;
		file_name: string;
		file_hash: string;
		file_size: number;
		captured_at: number;
		created_at: number;
		latitude: number;
		longitude: number;
		altitude: number;
		bearing: number;
		accuracy: number;
		width: number;
		height: number;
		upload_status: string;
		uploaded_at: number;
		retry_count: number;
		last_upload_attempt: number;
	}

	interface DevicePhotosResponse {
		photos: DevicePhoto[];
		last_updated: number;
		page: number;
		page_size: number;
		total_count: number;
		total_pages: number;
		has_more: boolean;
		error?: string;
	}

	let photosData: DevicePhotosResponse | null = null;
	let isLoading = true;
	let isLoadingMore = false;
	let error: string | null = null;
	let currentPage = 1;
	let pageSize = 20;

	onMount(() => {
		setTimeout(() => {
			fetchDevicePhotos();
		}, 10);
	});

	async function fetchDevicePhotos(page: number = 1, append: boolean = false) {
		try {
			if (append) {
				isLoadingMore = true;
			} else {
				isLoading = true;
			}

			const response = await invoke('plugin:hillview|get_device_photos', {
				page,
				page_size: pageSize
			}) as DevicePhotosResponse;

			console.log('🢄Device photos response:', JSON.stringify(response));

			if (append && photosData) {
				// Append new photos to existing data
				photosData.photos = [...photosData.photos, ...response.photos];
				photosData.page = response.page;
				photosData.has_more = response.has_more;
			} else {
				// Replace with new data
				photosData = response;
			}

			currentPage = response.page;
			error = response.error || null;
		} catch (err) {
			console.error('🢄Error fetching device photos:', err);
			error = `Failed to fetch device photos: ${err}`;
		} finally {
			isLoading = false;
			isLoadingMore = false;
		}
	}

	async function refreshDevicePhotos() {
		error = null;
		currentPage = 1;
		await fetchDevicePhotoStats();
		await fetchDevicePhotos(1, false);
	}

	async function loadMore() {
		if (photosData?.has_more && !isLoadingMore) {
			await fetchDevicePhotos(currentPage + 1, true);
		}
	}

	// async function refreshPhotoScan() {
	// 	try {
	// 		isLoading = true;
	// 		await invoke('plugin:hillview|refresh_photo_scan');
	// 		// Refresh the photos list after scan
	// 		await refreshDevicePhotos();
	// 	} catch (err) {
	// 		console.error('🢄Error refreshing photo scan:', err);
	// 		error = `Failed to refresh photo scan: ${err}`;
	// 	} finally {
	// 		isLoading = false;
	// 	}
	// }

	function formatFileSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
	}

	function formatDate(timestamp: number): string {
		return new Date(timestamp).toLocaleDateString();
	}

	function formatTime(timestamp: number): string {
		return new Date(timestamp).toLocaleTimeString();
	}

	function getStatusColor(status: string): string {
		switch (status) {
			case 'completed': return '#10b981'; // green
			case 'pending': return '#f59e0b'; // amber
			case 'uploading': return '#3b82f6'; // blue
			case 'failed': return '#ef4444'; // red
			default: return '#6b7280'; // gray
		}
	}

	function getStatusIcon(status: string) {
		switch (status) {
			case 'completed': return Upload;
			case 'pending': return Clock;
			case 'uploading': return RefreshCw;
			case 'failed': return AlertCircle;
			default: return Clock;
		}
	}
</script>

<StandardHeaderWithAlert
	title="Device Photos"
	showMenuButton={true}
	fallbackHref="/photos"
/>

<StandardBody>
	{#if error}
		<div class="error-message" data-testid="error-message">
			<AlertCircle size={20} />
			{error}
		</div>
	{/if}

	<div class="device-photos-section" data-testid="device-photos-section">
		<div class="section-header">
<!--			<div class="header-left">-->
<!--				<h2>Device Photos</h2>-->
<!--				{#if photosData}-->
<!--					<div class="photo-stats">-->
<!--						<span class="stat">-->
<!--							<Camera size={16} />-->
<!--							{photosData.total_count} photos-->
<!--						</span>-->
<!--						<span class="stat">-->
<!--							<Download size={16} />-->
<!--							Page {photosData.page} of {photosData.total_pages}-->
<!--						</span>-->
<!--					</div>-->
<!--				{/if}-->
<!--			</div>-->
			<div class="header-actions">
<!--				<button-->
<!--					class="action-button secondary"-->
<!--					on:click={refreshPhotoScan}-->
<!--					disabled={isLoading}-->
<!--					data-testid="scan-button"-->
<!--				>-->
<!--					<RefreshCw size={16} class={isLoading ? 'spinning' : ''} />-->
<!--					Scan Device-->
<!--				</button>-->
				<button
					class="action-button primary"
					on:click={refreshDevicePhotos}
					disabled={isLoading}
					data-testid="refresh-button"
				>
					<RefreshCw size={16} class={isLoading ? 'spinning' : ''} />
					{#if isLoading}
						Loading...
					{:else}
						Refresh
					{/if}
				</button>
			</div>
		</div>

		<DevicePhotoStats onRefresh={() => fetchDevicePhotos(1, false)} />

		{#if isLoading && !photosData}
			<div class="loading-container" data-testid="loading-container">
				<RefreshCw size={24} class="spinning" />
				<p>Loading device photos...</p>
			</div>
		{:else if photosData && photosData.photos.length > 0}
			<div class="photos-grid" data-testid="photos-grid">
				{#each photosData.photos as photo}
					<div class="photo-card" data-testid="photo-card">
						{#if $app.debug_enabled}
							<details>
								<summary>[debug]</summary>
								<pre>{JSON.stringify(photo, null, 2)}</pre>
							</details>
						{/if}

						<div class="photo-image">
							<img
								src={getDevicePhotoUrl(photo.file_path)}
								alt={photo.file_name}
								loading="lazy"
								data-testid="photo-thumbnail"
							/>
							<div class="photo-overlay">
								<div class="photo-status" style="color: {getStatusColor(photo.upload_status)}">
									<svelte:component this={getStatusIcon(photo.upload_status)} size={16} />
									{#if photo.upload_status === 'completed'}
										Uploaded
									{:else if photo.upload_status === 'pending'}
										upload Pending
									{:else if photo.upload_status === 'uploading'}
										Uploading
									{:else if photo.upload_status === 'failed'}
										upload Failed
									{:else}
										{photo.upload_status}
									{/if}
								</div>
							</div>
						</div>

						<div class="photo-header">
							<div class="photo-name">{photo.file_name}</div>
						</div>

						<div class="photo-details">
							<div class="detail-row">
								<span class="detail-label">Size:</span>
								<span class="detail-value">{formatFileSize(photo.file_size)}</span>
							</div>
							<div class="detail-row">
								<span class="detail-label">Date:</span>
								<span class="detail-value">{formatDate(photo.captured_at)}</span>
							</div>
							<div class="detail-row">
								<span class="detail-label">Time:</span>
								<span class="detail-value">{formatTime(photo.captured_at)}</span>
							</div>
							{#if photo.latitude !== 0 && photo.longitude !== 0}
								<div class="detail-row">
									<span class="detail-label">Location:</span>
									<span class="detail-value">
										<MapPin size={14} />
										{photo.latitude.toFixed(6)}, {photo.longitude.toFixed(6)}
									</span>
								</div>
							{/if}
							{#if photo.bearing !== 0}
								<div class="detail-row">
									<span class="detail-label">Bearing:</span>
									<span class="detail-value">{photo.bearing.toFixed(1)}°</span>
								</div>
							{/if}
							<div class="detail-row">
								<span class="detail-label">Dimensions:</span>
								<span class="detail-value">{photo.width} × {photo.height}</span>
							</div>
							{#if photo.retry_count > 0}
								<div class="detail-row">
									<span class="detail-label">Retries:</span>
									<span class="detail-value">{photo.retry_count}</span>
								</div>
							{/if}
						</div>

						<div class="photo-path">
							<span class="path-label">Path:</span>
							<span class="path-value">{photo.file_path}</span>
						</div>
						<RetryUploadsButton {photo} />
					</div>
				{/each}
			</div>

			{#if photosData.has_more}
				<div class="load-more-container">
					<button
						class="load-more-button"
						on:click={loadMore}
						disabled={isLoadingMore}
						data-testid="load-more-button"
					>
						{#if isLoadingMore}
							<RefreshCw size={16} class="spinning" />
							Loading more...
						{:else}
							<ChevronRight size={16} />
							Load More Photos
						{/if}
					</button>
				</div>
			{/if}
		{:else}
			<div class="no-data" data-testid="no-data">
				<Camera size={48} />
				<h3>No Device Photos Found</h3>
				<p>No photos have been detected on this device yet.</p>
<!--				<button class="action-button primary" on:click={refreshPhotoScan}>-->
<!--					<RefreshCw size={16} />-->
<!--					Scan for Photos-->
<!--				</button>-->
			</div>
		{/if}
	</div>
</StandardBody>

<style>
	.device-photos-section {
		padding: 0;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 24px;
		flex-wrap: wrap;
		gap: 16px;
	}

	.header-actions {
		display: flex;
		gap: 12px;
		flex-wrap: wrap;
	}

	.loading-container {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 60px 20px;
		color: #6b7280;
	}

	.loading-container p {
		margin-top: 12px;
		font-size: 1rem;
	}

	.photos-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 20px;
		margin-bottom: 24px;
	}

	.photo-card {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 20px;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
		transition: all 0.2s ease;
	}

	.photo-card:hover {
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
		transform: translateY(-2px);
	}

	.photo-image {
		position: relative;
		width: 100%;
		aspect-ratio: 1;
		border-radius: 8px;
		overflow: hidden;
		margin-bottom: 12px;
		background-color: #f3f4f6;
	}

	.photo-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform 0.3s ease;
	}

	.photo-card:hover .photo-image img {
		transform: scale(1.05);
	}

	.photo-overlay {
		position: absolute;
		top: 8px;
		right: 8px;
		background-color: rgba(0, 0, 0, 0.7);
		border-radius: 4px;
		padding: 4px 8px;
	}

	.photo-overlay .photo-status {
		color: white !important;
		font-size: 0.7rem;
	}

	.photo-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 16px;
		gap: 12px;
	}

	.photo-name {
		font-weight: 600;
		color: #1f2937;
		font-size: 1rem;
		word-break: break-word;
		flex: 1;
	}

	.photo-status {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.75rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		white-space: nowrap;
	}

	.photo-details {
		margin-bottom: 16px;
	}

	.detail-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 6px 0;
		border-bottom: 1px solid #f3f4f6;
		gap: 12px;
	}

	.detail-row:last-child {
		border-bottom: none;
	}

	.detail-label {
		font-size: 0.875rem;
		color: #6b7280;
		font-weight: 500;
		min-width: fit-content;
	}

	.detail-value {
		font-size: 0.875rem;
		color: #374151;
		text-align: right;
		display: flex;
		align-items: center;
		gap: 4px;
		word-break: break-word;
	}

	.photo-path {
		padding-top: 12px;
		border-top: 1px solid #f3f4f6;
	}

	.path-label {
		font-size: 0.75rem;
		color: #9ca3af;
		font-weight: 500;
		display: block;
		margin-bottom: 4px;
	}

	.path-value {
		font-size: 0.75rem;
		color: #6b7280;
		font-family: monospace;
		word-break: break-all;
		line-height: 1.4;
	}

	.load-more-container {
		display: flex;
		justify-content: center;
		margin: 32px 0;
	}

	.load-more-button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 24px;
		background-color: #f8fafc;
		color: #374151;
		border: 1px solid #e2e8f0;
		border-radius: 8px;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.load-more-button:hover:not(:disabled) {
		background-color: #f1f5f9;
		border-color: #cbd5e1;
		transform: translateY(-1px);
	}

	.load-more-button:disabled {
		opacity: 0.6;
		cursor: not-allowed;
		transform: none !important;
	}

	.no-data {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		text-align: center;
		color: #6b7280;
		padding: 60px 20px;
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
	}

	.no-data h3 {
		margin: 16px 0 8px 0;
		color: #374151;
		font-size: 1.25rem;
		font-weight: 600;
	}

	.no-data p {
		margin: 0 0 24px 0;
		font-size: 1rem;
	}

	.error-message {
		display: flex;
		align-items: center;
		gap: 12px;
		background-color: #fef2f2;
		color: #dc2626;
		padding: 16px;
		border-radius: 8px;
		border: 1px solid #fecaca;
		margin-bottom: 24px;
		font-weight: 500;
	}

	/* Spinning animation for loading icons */
	:global(.spinning) {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}

	/* Responsive adjustments */
	@media (max-width: 768px) {
		.section-header {
			flex-direction: column;
			align-items: stretch;
		}

		.header-actions {
			justify-content: stretch;
		}

		.action-button {
			flex: 1;
			justify-content: center;
		}

		.photos-grid {
			grid-template-columns: 1fr;
			gap: 16px;
		}

		.photo-header {
			flex-direction: column;
			align-items: stretch;
			gap: 8px;
		}

		.photo-status {
			align-self: flex-start;
		}
	}
</style>
