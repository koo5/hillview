<script lang="ts">
	import {onMount} from 'svelte';
	import {get} from 'svelte/store';
	import {myGoto} from '$lib/navigation.svelte';
	import { Trash2, Map, Settings, ThumbsUp, ThumbsDown} from 'lucide-svelte';
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import Spinner from '../../components/Spinner.svelte';
	import PhotoImport from '$lib/components/PhotoImport.svelte';
	import PhotoUpload from '$lib/components/PhotoUpload.svelte';
	import {auth, checkAuth} from '$lib/auth.svelte';
	import {userId} from '$lib/authStore';
	import type {UserPhoto} from '$lib/stores';
	import type {User} from '$lib/auth.svelte';
	import {http, handleApiError, TokenExpiredError} from '$lib/http';
	import {TAURI} from '$lib/tauri';
	import {navigateWithHistory} from '$lib/navigation.svelte';
	import {invoke} from '@tauri-apps/api/core';

	let photos: UserPhoto[] = [];
	let isLoading = true;
	let error: string | null = null;
	let nextCursor: string | null = null;
	let hasMore = false;
	let loadingMore = false;
	let totalCount = 0;
	let autoUploadEnabled = false;
	let showSettings = false;
	let user: User | null = null;
	let activityLog: Array<{ timestamp: Date, message: string, type: 'success' | 'warning' | 'error' | 'info' }> = [];
	let activeTab: 'upload' | 'import' = TAURI ? 'import' : 'upload';


	function addLogEntry(message: string, type: 'success' | 'warning' | 'error' | 'info' = 'info') {
		console.info(`🢄 Log entry [${type}]: ${message}`);
		activityLog = [{
			timestamp: new Date(),
			message,
			type
		}, ...activityLog.slice(0, 9)]; // Keep only last 10 entries
	}

	function formatLogTime(timestamp: Date): string {
		return timestamp.toLocaleTimeString();
	}


	onMount(() => {
		// Check authentication status first (async)
		checkAuth();

		// Subscribe to userId changes to avoid reactive loops from auth store updates during token refresh
		const unsubscribe = userId.subscribe(async (currentUserId) => {

			console.info(`🢄 [/PHOTOS] userId changed: ${currentUserId}, reloading photos...`);

			// Get the current auth state when userId changes
			const currentAuth = get(auth);
			user = currentAuth.isAuthenticated ? currentAuth.user : null;

			if (currentUserId && user) {
				// Load auto-upload setting from Android if running on Tauri
				if (TAURI) {
					await loadAndroidAutoUploadSetting();
				}

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
		console.log(`DEBUG: deletePhoto called with photoId: ${photoId}`);
		if (!confirm('Are you sure you want to delete this photo?')) {
			console.log('🢄DEBUG: User cancelled delete');
			return;
		}

		console.log(`DEBUG: Attempting to delete photo: ${photoId}`);

		try {
			const response = await http.delete(`/photos/${photoId}`);

			console.log(`DEBUG: Delete response status: ${response.status}`);

			if (!response.ok) {
				const errorText = await response.text();
				console.log(`DEBUG: Delete failed with response: ${errorText}`);
				throw new Error(`Failed to delete photo: ${response.status} ${errorText}`);
			}

			console.log('🢄DEBUG: Delete successful, removing from UI');

			// Find the photo name for logging
			const deletedPhoto = photos.find(photo => photo.id === photoId);
			const photoName = deletedPhoto?.original_filename || `Photo ${photoId}`;

			// Remove the photo from the list
			photos = photos.filter(photo => photo.id !== photoId);

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

	async function loadAndroidAutoUploadSetting() {
		try {
			const result = await invoke('plugin:hillview|get_upload_status') as { autoUploadEnabled: boolean };
			autoUploadEnabled = result.autoUploadEnabled || false;
			console.log('📱 Loaded Android auto-upload setting:', autoUploadEnabled);
		} catch (err) {
			console.error('🢄Error loading Android auto-upload setting:', err);
			autoUploadEnabled = false; // Default to false if we can't read it
		}
	}

	async function saveSettings() {
		// update the Android background service setting
		if (TAURI) {
			try {
				console.log('📤 Setting Android auto-upload to:', autoUploadEnabled);
				await invoke('plugin:hillview|set_auto_upload_enabled', {enabled: autoUploadEnabled});
				addLogEntry(`Android auto-upload ${autoUploadEnabled ? 'enabled' : 'disabled'}`, 'success');
			} catch (pluginErr) {
				console.error('🢄Error updating Android plugin:', pluginErr);
				addLogEntry('Warning: Android auto-upload setting may not be updated', 'warning');
			}
		}

		showSettings = false;
		addLogEntry('Settings saved successfully', 'success');
	}

	function formatDate(dateString: string) {
		const date = new Date(dateString);
		return date.toLocaleString();
	}

	function viewOnMap(photo: UserPhoto) {
		if (photo.latitude && photo.longitude) {
			myGoto(`/?lat=${photo.latitude}&lon=${photo.longitude}&zoom=18`);
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
		console.log(`Setting ${rating} for photo ${photoId}`);

		try {
			const response = await http.post(`/ratings/hillview/${photoId}`, { rating });

			if (!response.ok) {
				throw new Error(`Failed to set rating: ${response.status}`);
			}

			const data = await response.json();
			console.log('Rating response:', data);

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
			console.error('Error setting rating:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`Rating failed: ${errorMessage}`, 'error');
		}
	}

	async function removePhotoRating(photoId: number) {
		console.log(`Removing rating for photo ${photoId}`);

		try {
			const response = await http.delete(`/ratings/hillview/${photoId}`);

			if (!response.ok) {
				throw new Error(`Failed to remove rating: ${response.status}`);
			}

			const data = await response.json();
			console.log('Rating removal response:', data);

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
			console.error('Error removing rating:', err);
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
	title="My Photos"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	{#if TAURI}
		<div class="page-actions">
			<button class="settings-button" on:click={() => showSettings = !showSettings}>
				<Settings size={20}/>
				Settings
			</button>
		</div>
	{/if}
	{#if error}
		<div class="error-message">{error}</div>
	{/if}

	{#if TAURI && showSettings}
		<div class="settings-panel">
			<h2>Auto-Upload Settings</h2>
			<div class="form-group">
				<label>
					<input type="checkbox" bind:checked={autoUploadEnabled} data-testid="auto-upload-checkbox"/>
					Enable auto-upload
				</label>
				<p class="help-text">
					Automatically upload photos taken with the app's camera to your account.
				</p>
				{#if !user}
					<div class="login-notice {autoUploadEnabled ? 'urgent-login-notice' : ''}">
						<p>Please
							<button type="button" class="login-link" on:click={goToLogin}>log in</button>
							to upload photos.
						</p>
					</div>
				{/if}
			</div>

			<div class="button-group">
				<button class="secondary-button" on:click={() => showSettings = false}>Cancel</button>
				<button class="primary-button" on:click={saveSettings} data-testid="save-settings-button"
						disabled={!user}>Save Settings
				</button>
			</div>
		</div>
	{/if}

	<div class="photo-management-section" data-testid="photo-management-section">
		<div class="tabs-header">
			<h2>Photo Management</h2>
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
					<button
						class="tab-button"
						class:active={activeTab === 'import'}
						on:click={() => activeTab = 'import'}
						data-testid="import-tab"
					>
						Import from Directory
					</button>
				{/if}
			</div>
		</div>

		<div class="tab-content">
			{#if activeTab === 'upload'}
				<PhotoUpload
					{user}
					onLogEntry={addLogEntry}
					onUploadComplete={handleUploadComplete}
					{goToLogin}
				/>
			{:else if activeTab === 'import'}
				<PhotoImport
					{user}
					onLogEntry={addLogEntry}
					onImportComplete={handleImportComplete}
					{goToLogin}
				/>
			{/if}
		</div>
	</div>


	{#if activityLog.length > 0}
		<div class="activity-log">
			<h2>Recent Activity</h2>
			<div class="log-entries">
				{#each activityLog as entry (entry.timestamp)}
					<div class="log-entry log-{entry.type}">
						<span class="log-time">{formatLogTime(entry.timestamp)}</span>
						<span class="log-message">{entry.message}</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<div class="photos-grid" data-testid="photos-grid">
		<h2>My Photos ({totalCount})</h2>

		{#if isLoading}
			<div class="loading-container" data-testid="loading-container">
				<Spinner/>
				<p>Loading your photos...</p>
			</div>
		{:else if photos.length === 0}
			<p class="no-photos" data-testid="no-photos-message">
				{#if user}
					You haven't uploaded any photos yet.
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

							<details>
								<summary>?</summary>
								<pre>{JSON.stringify(photo, null, 2)}</pre>
							</details>

						<div class="photo-image">
							<img
								src={photo.sizes?.['320']?.url}
								alt={photo.description || photo.original_filename}
								data-testid="photo-thumbnail"
							/>
						</div>
						<div class="photo-info">
							<h3 data-testid="photo-filename">{photo.original_filename}</h3>
							{#if photo.description}
								<p class="description">{photo.description}</p>
							{/if}
							<p class="meta">Uploaded: {formatDate(photo.uploaded_at || photo.created_at)}</p>
							{#if photo.captured_at}
								<p class="meta">Captured: {formatDate(photo.captured_at)}</p>
							{/if}
							<div class="photo-actions">
								{#if photo.latitude && photo.longitude}
									<button class="action-button" on:click={() => viewOnMap(photo)}>
										<Map size={16}/>
										View on Map
									</button>
								{/if}
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
						</div>
					</div>
				{/each}
			</div>

			<!-- Load More Button -->
			{#if hasMore}
				<div class="load-more-container">
					<button
						class="load-more-button"
						on:click={loadMorePhotos}
						disabled={loadingMore}
						data-testid="load-more-button"
					>
						{#if loadingMore}
							<Spinner/>
							Loading more...
						{:else}
							Load More Photos
						{/if}
					</button>
				</div>
			{/if}
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
		justify-content: flex-end;
		margin-bottom: 16px;
	}

	h2 {
		margin-top: 0;
		color: #444;
	}

	.settings-button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 16px;
		background-color: #f5f5f5;
		border: 1px solid #ddd;
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 0.3s;
	}

	.settings-button:hover {
		background-color: #e5e5e5;
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
		gap: 8px;
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

	.tab-content {
		padding-top: 20px;
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
		gap: 8px;
		margin-top: 12px;
	}

	.action-button {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 6px 12px;
		background-color: #f5f5f5;
		border: 1px solid #ddd;
		border-radius: 4px;
		font-size: 14px;
		cursor: pointer;
		transition: background-color 0.3s;
	}

	.action-button:hover {
		background-color: #e5e5e5;
	}

	.action-button.delete {
		color: #e53935;
	}

	.action-button.delete:hover {
		background-color: #ffebee;
	}

	.action-button.rating {
		color: #6b7280;
		position: relative;
	}

	.action-button.rating:hover {
		background-color: #f0f9ff;
		color: #1e40af;
	}

	.action-button.rating.active {
		background-color: #dbeafe;
		color: #1e40af;
		border-color: #3b82f6;
	}

	.action-button.rating.active:hover {
		background-color: #bfdbfe;
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

	.login-notice {
		background: #fff3cd;
		color: #856404;
		padding: 0.75em;
		border-radius: 6px;
		margin-top: 0.5em;
	}

	.urgent-login-notice {
		background: #f8d7da;
		color: #721c24;
		font-weight: bold;
		border: 2px solid #dc3545;
		animation: urgentPulse 1s infinite alternate;
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
	}

	@media (max-width: 480px) {
		.grid {
			grid-template-columns: 1fr;
		}

		.photo-actions {
			flex-direction: column;
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

	/* Load More Button Styles */
	.load-more-container {
		display: flex;
		justify-content: center;
		margin-top: 32px;
		padding: 20px 0;
	}

	.load-more-button {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 24px;
		background-color: #4a90e2;
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 16px;
		font-weight: 500;
		cursor: pointer;
		transition: background-color 0.3s, transform 0.2s;
		min-width: 160px;
		justify-content: center;
	}

	.load-more-button:hover:not(:disabled) {
		background-color: #357abd;
		transform: translateY(-1px);
	}

	.load-more-button:disabled {
		background-color: #94a3b8;
		cursor: not-allowed;
		transform: none;
	}

</style>
