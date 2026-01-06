<svelte:head>
	<title>My Photos - Hillview</title>
</svelte:head>

<script lang="ts">
	import {app} from '$lib/data.svelte';
	import {onMount} from 'svelte';
	import {get} from 'svelte/store';
	import {myGoto} from '$lib/navigation.svelte';
	import {constructPhotoMapUrl} from '$lib/urlUtils';
	import {Trash2, Map, Settings, ThumbsUp, ThumbsDown, Upload} from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import PhotoImport from '$lib/components/PhotoImport.svelte';
	import PhotoUpload from '$lib/components/PhotoUpload.svelte';
	import {auth} from '$lib/auth.svelte';
	import {userId} from '$lib/authStore';
	import type {UserPhoto} from '$lib/stores';
	import type {User} from '$lib/auth.svelte';
	import type {ActivityLogEntry} from '$lib/types/activityLog';
	import {http, handleApiError, TokenExpiredError} from '$lib/http';
	import {TAURI} from '$lib/tauri';
	import {navigateWithHistory} from '$lib/navigation.svelte';
	import UploadSettingsComponent from '$lib/components/UploadSettings.svelte';
	import {invoke} from "@tauri-apps/api/core";
	import LoadMoreButton from "$lib/components/LoadMoreButton.svelte";
	import LicenseSelector from '$lib/components/LicenseSelector.svelte';
	import {photoLicense} from '$lib/data.svelte';
	import RetryUploadsButton from "$lib/components/RetryUploadsButton.svelte";
	import DevicePhotoStats from "$lib/components/DevicePhotoStats.svelte";

	let photos: UserPhoto[] = [];
	let isLoading = true;
	let error: string | null = null;
	let nextCursor: string | null = null;
	let hasMore = false;
	let loadingMore = false;
	let totalCount = 0;
	let showSettings = false;
	let user: User | null = null;
	let activityLog: ActivityLogEntry[] = [];
	//let activeTab: 'upload' | 'import' = TAURI ? 'import' : 'upload';
	let activeTab: 'upload' | 'import' = 'upload';


	function addLogEntry(
		message: string,
		type: 'success' | 'warning' | 'error' | 'info' = 'info',
		metadata?: ActivityLogEntry['metadata']
	) {
		console.info(`🢄 Log entry [${type}]: ${message}`);
		activityLog = [{
			timestamp: new Date(),
			message,
			type,
			metadata
		}, ...activityLog.slice(0, 9)]; // Keep only last 10 entries
	}

	function formatLogTime(timestamp: Date): string {
		return timestamp.toLocaleTimeString();
	}


	onMount(() => {
		// Subscribe to userId changes to avoid reactive loops from auth store updates during token refresh
		const unsubscribe = userId.subscribe(async (currentUserId) => {

			console.info(`🢄 [/PHOTOS] userId changed: ${currentUserId}, reloading photos...`);

			// Get the current auth state when userId changes
			const currentAuth = get(auth);
			user = currentAuth.is_authenticated ? currentAuth.user : null;

			if (currentUserId && user) {
				// Fetch user photos when authenticated
				try {
					await fetchPhotos(true); // Reset and fetch from the beginning
				} catch (err) {
					console.error('🢄Error loading photos:', err);
					error = handleApiError(err);

					// TokenExpiredError is handled automatically by the http client
					if (err instanceof TokenExpiredError) {
						// No need to handle manually, http client already logged out
						return;
					}
				} finally {
					isLoading = false;
				}
			} else {
				// Show empty state for non-authenticated users
				photos = [];
				isLoading = false;
			}
		});


		// Return cleanup function
		return unsubscribe;
	});


	async function fetchPhotoCount() {
		try {
			const response = await http.get('/photos/count');
			if (!response.ok) {
				throw new Error(`Failed to fetch photo count: ${response.status}`);
			}
			const data = await response.json();
			totalCount = data.counts?.total || 0;
		} catch (err) {
			console.error('🢄Error fetching photo count:', err);
		}
	}

	async function fetchPhotos(reset = false) {
		try {
			if (reset) {
				photos = [];
				nextCursor = null;
				hasMore = false;
				totalCount = 0;
			}

			const url = nextCursor ? `/photos/?cursor=${encodeURIComponent(nextCursor)}` : '/photos/';
			const response = await http.get(url);

			if (!response.ok) {
				throw new Error(`Failed to fetch photos: ${response.status}`);
			}

			const data = await response.json();

			const newPhotos = data.photos || [];
			if (reset) {
				photos = newPhotos;
			} else {
				photos = [...photos, ...newPhotos];
			}

			nextCursor = data.pagination?.next_cursor || null;
			hasMore = data.pagination?.has_more || false;
			totalCount = data.counts?.total || 0;

		} catch (err) {
			console.error('🢄Error fetching photos:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(errorMessage, 'error');
			error = errorMessage;

			// TokenExpiredError is handled automatically by the http client
			if (err instanceof TokenExpiredError) {
				// No need to handle manually, http client already logged out
				return;
			}
		}
	}

	async function loadMorePhotos() {
		if (!hasMore || loadingMore) return;

		loadingMore = true;
		try {
			await fetchPhotos(false);
		} finally {
			loadingMore = false;
		}
	}

	async function handleUploadComplete() {
		await fetchPhotos(true); // Reset and fetch from the beginning
	}

	async function deletePhoto(photoId: number) {
		console.log(`🢄DEBUG: deletePhoto called with photoId: ${photoId}`);
		if (!confirm('Are you sure you want to delete this photo?')) {
			console.log('🢄DEBUG: User cancelled delete');
			return;
		}

		console.log(`🢄DEBUG: Attempting to delete photo: ${photoId}`);

		try {
			const response = await http.delete(`/photos/${photoId}`);

			console.log(`🢄DEBUG: Delete response status: ${response.status}`);

			if (!response.ok) {
				const errorText = await response.text();
				console.log(`🢄DEBUG: Delete failed with response: ${errorText}`);
				throw new Error(`Failed to delete photo: ${response.status} ${errorText}`);
			}

			console.log('🢄DEBUG: Delete successful, removing from UI');

			// Find the photo name for logging
			const deletedPhoto = photos.find(photo => photo.id === photoId);
			const photoName = deletedPhoto?.original_filename || `Photo ${photoId}`;

			// Remove the photo from the list
			photos = photos.filter(photo => photo.id !== photoId);

			// Refresh just the count
			await fetchPhotoCount();

			addLogEntry(`Deleted: ${photoName}`, 'success');

		} catch (err) {
			console.error('🢄Error deleting photo:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`Delete failed: ${errorMessage}`, 'error');
			error = errorMessage;

			// TokenExpiredError is handled automatically by the http client
			if (err instanceof TokenExpiredError) {
				// No need to handle manually, http client already logged out
				return;
			}
		}
	}


	function formatDate(dateString: string) {
		const date = new Date(dateString);
		return date.toLocaleString();
	}

	function viewOnMap(photo: UserPhoto) {
		if (photo.latitude && photo.longitude) {
			myGoto(constructPhotoMapUrl(photo));
		}
	}

	function goToLogin() {
		navigateWithHistory('/login');
	}

	async function handleImportComplete(importedCount: number) {
		if (importedCount > 0) {
			// Refresh the photos list to show imported photos
			await fetchPhotos(true); // Reset and fetch from the beginning
		}
	}

	async function setPhotoRating(photoId: number, rating: 'thumbs_up' | 'thumbs_down') {
		console.log(`🢄Setting ${rating} for photo ${photoId}`);

		try {
			const response = await http.post(`/ratings/hillview/${photoId}`, {rating});

			if (!response.ok) {
				throw new Error(`Failed to set rating: ${response.status}`);
			}

			const data = await response.json();
			console.log('🢄Rating response:', data);

			// Update the photo in our local array
			photos = photos.map(photo => {
				if (photo.id === photoId) {
					return {
						...photo,
						user_rating: data.user_rating,
						rating_counts: data.rating_counts
					};
				}
				return photo;
			});

			addLogEntry(`Rated photo ${rating.replace('_', ' ')}`, 'success');

		} catch (err) {
			console.error('🢄Error setting rating:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`Rating failed: ${errorMessage}`, 'error');
		}
	}

	async function removePhotoRating(photoId: number) {
		console.log(`🢄Removing rating for photo ${photoId}`);

		try {
			const response = await http.delete(`/ratings/hillview/${photoId}`);

			if (!response.ok) {
				throw new Error(`Failed to remove rating: ${response.status}`);
			}

			const data = await response.json();
			console.log('🢄Rating removal response:', data);

			// Update the photo in our local array
			photos = photos.map(photo => {
				if (photo.id === photoId) {
					return {
						...photo,
						user_rating: null,
						rating_counts: data.rating_counts
					};
				}
				return photo;
			});

			addLogEntry('Rating removed', 'success');

		} catch (err) {
			console.error('🢄Error removing rating:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`Rating removal failed: ${errorMessage}`, 'error');
		}
	}

	async function handleRatingClick(photoId: number, rating: 'thumbs_up' | 'thumbs_down') {
		const photo = photos.find(p => p.id === photoId);
		if (!photo) return;

		// If user clicks the same rating they already have, remove it
		if (photo.user_rating === rating) {
			await removePhotoRating(photoId);
		} else {
			// Otherwise set/change the rating
			await setPhotoRating(photoId, rating);
		}
	}
</script>

<StandardHeaderWithAlert
	title={"My Photos" + ' (' + totalCount + ')'}
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	{#if TAURI}

		<div class="page-actions">
			<button class="action-button primary" on:click={() => showSettings = !showSettings}>
				<Settings size={20}/>
				Settings
			</button>
			<button class="action-button primary" on:click={() => myGoto('/device-photos')}
					data-testid="device-photos-button">
				Device Photos
			</button>
		</div>
	{/if}
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	{#if TAURI && showSettings}
		<div class="settings-panel">
			<UploadSettingsComponent
				onSaveSuccess={(message) => {
					addLogEntry(message, 'success');
					showSettings = false;
				}}
				onCancel={() => showSettings = false}
			/>
		</div>
	{/if}

	<DevicePhotoStats addLogEntry={addLogEntry} onRefresh={() => fetchPhotos(true)} />

	{#if !TAURI}
		<div class="photo-management-section" data-testid="photo-management-section">
			<div class="tabs-header">
				<h2>Upload Photos</h2>
				<div class="tabs">
					{#if !TAURI}
						<button
							class="tab-button"
							class:active={activeTab === 'upload'}
							on:click={() => activeTab = 'upload'}
							data-testid="upload-tab"
						>
							Upload Photos
						</button>
					{:else}
						{#if $app.debug_enabled}
							<button
								class="tab-button"
								class:active={activeTab === 'import'}
								on:click={() => activeTab = 'import'}
								data-testid="import-tab"
							>
								Import from Directory
							</button>
						{/if}
					{/if}
				</div>
			</div>

			{#if !TAURI && activeTab === 'upload'}
				<div class="tab-content">
					{#if activeTab === 'upload'}
						{#if !TAURI}
							<LicenseSelector required={true}/>
							<PhotoUpload
								{user}
								onLogEntry={addLogEntry}
								onUploadComplete={handleUploadComplete}
								{goToLogin}
								disabled={$photoLicense === null}
							/>
						{/if}
					{:else if activeTab === 'import'}
						<div class="license-section">
							<LicenseSelector required={true}/>
						</div>
						<PhotoImport
							{user}
							onLogEntry={addLogEntry}
							onImportComplete={handleImportComplete}
							{goToLogin}
							disabled={$photoLicense === null}
						/>
					{/if}
				</div>
			{/if}
		</div>


		{#if activityLog.length > 0}
			<div class="activity-log" data-testid="activity-log">
				<h2>Recent Activity</h2>
				<div class="log-entries" data-testid="log-entries">
					{#each activityLog as entry (entry.timestamp)}
						<div
							class="log-entry log-{entry.type}"
							data-testid="log-entry"
							data-log-type="{entry.type}"
							data-operation="{entry.metadata?.operation || ''}"
							data-filename="{entry.metadata?.filename || ''}"
							data-photo-id="{entry.metadata?.photo_id || ''}"
							data-outcome="{entry.metadata?.outcome || ''}"
						>
							<span class="log-time">{formatLogTime(entry.timestamp)}</span>
							<span class="log-message">{entry.message}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}

	<div class="photos-grid" data-testid="photos-grid">
		{#if !TAURI}
			<h2>My Photos ({totalCount})</h2>
		{/if}

		{#if isLoading}
			<div class="loading-container" data-testid="loading-container">
				<Spinner/>
				<p>Loading your photos...</p>
			</div>
		{:else if photos.length === 0}
			<p class="no-photos" data-testid="no-photos-message">
				{#if user}
					{#if !error}
						You haven't uploaded any photos yet.
					{:else}
						There was an error loading photos.
					{/if}
				{:else}
					Please
					<button type="button" class="login-link" on:click={goToLogin}>log in</button>
					to view your photos.
				{/if}
			</p>
		{:else}
			<div class="grid" data-testid="photos-list">
				{#each photos as photo (photo.id)}
					<div class="photo-card" data-testid="photo-card" data-photo-id={photo.id}
						 data-filename={photo.original_filename}>

						{#if $app.debug_enabled}
							<details>
								<summary>[debug]</summary>
								<pre>{JSON.stringify(photo, null, 2)}</pre>
							</details>
						{/if}

						<button class="photo-image" on:click={() => viewOnMap(photo)} type="button">
							<img
								src={photo.sizes?.['320']?.url}
								alt={photo.description || photo.original_filename}
								data-testid="photo-thumbnail"
							/>
						</button>
						<div class="photo-info">
							<h3 data-testid="photo-filename">{photo.original_filename}</h3>
							{#if photo.description}
								<p class="description">{photo.description}</p>
							{/if}
							<p class="meta">
								Uploaded: {photo.uploaded_at ? formatDate(photo.uploaded_at) : 'Unknown'}</p>
							{#if photo.captured_at}
								<p class="meta">Captured: {formatDate(photo.captured_at)}</p>
							{/if}
							<div class="photo-actions">
								<button
									class="action-button rating {photo.user_rating === 'thumbs_up' ? 'active' : ''}"
									data-testid="thumbs-up-button"
									data-photo-id={photo.id}
									on:click={() => handleRatingClick(photo.id, 'thumbs_up')}
								>
									<ThumbsUp size={16}/>
									<span class="rating-count">
										{photo.rating_counts?.thumbs_up || 0}
									</span>
								</button>
								<button
									class="action-button rating {photo.user_rating === 'thumbs_down' ? 'active' : ''}"
									data-testid="thumbs-down-button"
									data-photo-id={photo.id}
									on:click={() => handleRatingClick(photo.id, 'thumbs_down')}
								>
									<ThumbsDown size={16}/>
									<span class="rating-count">
										{photo.rating_counts?.thumbs_down || 0}
									</span>
								</button>
								<button class="action-button delete" data-testid="delete-photo-button"
										data-photo-id={photo.id} on:click={() => deletePhoto(photo.id)}>
									<Trash2 size={16}/>
									Delete
								</button>
							</div>
							<RetryUploadsButton {photo} {addLogEntry} />
						</div>
					</div>
				{/each}
			</div>

			<LoadMoreButton
				hasMore={hasMore && !isLoading}
				loading={loadingMore}
				onLoadMore={loadMorePhotos}
			/>
		{/if}
	</div>
</StandardBody>

<style>
	.photos-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 20px;
	}

	.page-actions {
		display: flex;
		gap: 12px;
		margin-bottom: 20px;
		flex-wrap: wrap;
		justify-content: center;
	}

	h2 {
		margin-top: 0;
		color: #444;
	}

	.settings-panel {
		background-color: #f9f9f9;
		border: 1px solid #ddd;
		border-radius: 8px;
		padding: 20px;
		margin-bottom: 24px;
	}

	.help-text {
		font-size: 14px;
		color: #666;
		margin-top: 4px;
	}

	.button-group {
		display: flex;
		gap: 12px;
		margin-top: 20px;
	}

	.photo-management-section {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
		margin-bottom: 32px;
	}

	.tabs-header {
		margin-bottom: 24px;
	}

	.tabs-header h2 {
		margin: 0 0 16px 0;
		color: #444;
	}

	.tabs {
		display: flex;
		border-bottom: 1px solid #e2e8f0;
		margin-bottom: 0;
	}

	.tab-button {
		padding: 12px 20px;
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		color: #6b7280;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
		white-space: nowrap;
	}

	.tab-button:hover {
		color: #374151;
		background-color: #f8fafc;
	}

	.tab-button.active {
		color: #4a90e2;
		border-bottom-color: #4a90e2;
		background-color: transparent;
	}



	.secondary-button {
		padding: 12px 24px;
		background-color: #f5f5f5;
		color: #333;
		border: 1px solid #ddd;
		border-radius: 4px;
		font-size: 16px;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.3s;
	}

	.secondary-button:hover {
		background-color: #e5e5e5;
	}


	.activity-log {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
		margin-bottom: 32px;
	}

	.activity-log h2 {
		margin-top: 0;
		margin-bottom: 16px;
		color: #444;
		font-size: 18px;
	}

	.log-entries {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.log-entry {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 12px;
		border-radius: 4px;
		font-size: 14px;
		border-left: 4px solid;
	}

	.log-entry.log-success {
		background-color: #f0f9ff;
		border-left-color: #10b981;
		color: #064e3b;
	}

	.log-entry.log-warning {
		background-color: #fffbeb;
		border-left-color: #f59e0b;
		color: #92400e;
	}

	.log-entry.log-error {
		background-color: #fef2f2;
		border-left-color: #ef4444;
		color: #991b1b;
	}

	.log-entry.log-info {
		background-color: #f8fafc;
		border-left-color: #6b7280;
		color: #374151;
	}

	.log-time {
		font-family: monospace;
		font-size: 12px;
		opacity: 0.7;
		min-width: 80px;
	}

	.log-message {
		flex: 1;
	}

	.photos-grid {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		padding: 24px;
	}

	.loading-container {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 40px 0;
	}

	.no-photos {
		text-align: center;
		color: #666;
		padding: 40px 0;
	}

	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: 24px;
		margin-top: 16px;
	}

	.photo-card {
		border: 1px solid #eee;
		border-radius: 8px;
		overflow: hidden;
		transition: transform 0.3s, box-shadow 0.3s;
	}

	.photo-card:hover {
		transform: translateY(-4px);
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
	}

	.photo-image {
		height: 200px;
		overflow: hidden;
		width: 100%;
		padding: 0;
		border: none;
		background: none;
		cursor: pointer;
		display: block;
	}

	.photo-image img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		transition: transform 0.3s;
	}

	.photo-card:hover .photo-image img {
		transform: scale(1.05);
	}

	.photo-info {
		padding: 16px;
	}

	.photo-info h3 {
		margin: 0 0 8px 0;
		font-size: 18px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.description {
		color: #555;
		margin: 0 0 12px 0;
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.meta {
		font-size: 14px;
		color: #777;
		margin: 4px 0;
	}

	.photo-actions {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		margin-top: 12px;
	}

	.rating-count {
		font-size: 12px;
		font-weight: 600;
		min-width: 16px;
		text-align: center;
	}

	.error-message {
		background-color: #ffebee;
		color: #c62828;
		padding: 12px;
		border-radius: 4px;
		margin-bottom: 20px;
	}


	@keyframes urgentPulse {
		0% {
			box-shadow: 0 0 0 0 #dc3545;
		}
		100% {
			box-shadow: 0 0 10px 2px #dc3545;
		}
	}

	/* Import section styles */
	.import-section {
		background-color: #f8f9fa;
		border: 1px solid #e9ecef;
		border-radius: 8px;
		padding: 20px;
		margin-bottom: 30px;
	}


	.import-description {
		color: #6c757d;
		font-size: 14px;
		margin-bottom: 16px;
		line-height: 1.4;
	}


	/* Responsive adjustments */
	@media (max-width: 768px) {
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		}

		.page-actions {
			justify-content: stretch;
		}

		.page-actions .action-button {
			flex: 1;
			justify-content: center;
		}
	}

	@media (max-width: 480px) {
		.grid {
			grid-template-columns: 1fr;
		}
	}

	.login-link {
		background: none;
		border: none;
		color: #1565c0;
		text-decoration: underline;
		font-weight: 500;
		cursor: pointer;
		padding: 0;
		font-size: inherit;
		font-family: inherit;
	}

	.login-link:hover {
		color: #0d47a1;
	}
</style>
