<script lang="ts">
	import {onMount} from 'svelte';
	import {myGoto} from '$lib/navigation.svelte';
	import {Upload, Trash2, Map, Settings} from 'lucide-svelte';
	import BackButton from '../../components/BackButton.svelte';
	import Spinner from '../../components/Spinner.svelte';
	import {auth, checkAuth} from '$lib/auth.svelte';
	import {app} from '$lib/data.svelte';
	import type {UserPhoto} from '$lib/stores';
	import type {User} from '$lib/auth.svelte';
	import {http, handleApiError, TokenExpiredError} from '$lib/http';
	import {backendUrl} from '$lib/config';
	import {TAURI} from '$lib/tauri';
	import {secureUploadFiles} from '$lib/secureUpload';
	import {navigateWithHistory} from '$lib/navigation.svelte';
	import {invoke} from '@tauri-apps/api/core';

	let photos: UserPhoto[] = [];
	let isLoading = true;
	let error: string | null = null;
	let uploadFiles: File[] = [];
	let description = '';
	let isPublic = true;
	let isUploading = false;
	let uploadProgress = 0;
	let autoUploadEnabled = false;
	let showSettings = false;
	let user: User | null = null;
	let activityLog: Array<{ timestamp: Date, message: string, type: 'success' | 'warning' | 'error' | 'info' }> = [];

	function addLogEntry(message: string, type: 'success' | 'warning' | 'error' | 'info' = 'info') {
		activityLog = [{
			timestamp: new Date(),
			message,
			type
		}, ...activityLog.slice(0, 9)]; // Keep only last 10 entries
	}

	function formatLogTime(timestamp: Date): string {
		return timestamp.toLocaleTimeString();
	}

	function autoResizeTextarea(event: Event) {
		const textarea = event.target as HTMLTextAreaElement;
		textarea.style.height = 'auto';
		textarea.style.height = `${textarea.scrollHeight}px`;
	}

	onMount(async () => {
		// Check authentication status first
		checkAuth();

		// Check if user is authenticated
		auth.subscribe(async (value) => {
			user = value.isAuthenticated ? value.user : null;
			if (user) {
				autoUploadEnabled = user.auto_upload_enabled || false;

				// Fetch user photos when authenticated
				try {
					await fetchPhotos();
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
	});

	async function fetchPhotos() {
		try {
			const response = await http.get('/photos');

			if (!response.ok) {
				throw new Error(`Failed to fetch photos: ${response.status}`);
			}

			photos = await response.json();

			// Update app store with user photos
			app.update(a => ({
				...a,
				userPhotos: photos
			}));
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

	async function handleUpload() {
		if (!uploadFiles.length) return;

		isUploading = true;
		uploadProgress = 0;

		const totalFiles = uploadFiles.length;
		addLogEntry(`Starting secure batch upload: ${totalFiles} file${totalFiles > 1 ? 's' : ''}`, 'info');

		try {
			// Use new secure upload service
			const uploadResult = await secureUploadFiles(
				uploadFiles,
				description,
				isPublic,
				undefined, // Use default worker URL
				(completed, total, currentFile) => {
					uploadProgress = Math.round((completed / total) * 100);
					if (currentFile) {
						addLogEntry(`Uploading ${completed + 1}/${total}: ${currentFile}`, 'info');
					}
				}
			);

			// Process results
			uploadResult.results.forEach((result, index) => {
				const file = uploadFiles[index];
				if (result.success) {
					addLogEntry(`✅ Uploaded: ${file.name}`, 'success');
				} else {
					addLogEntry(`❌ Failed: ${file.name} - ${result.error}`, 'error');
				}
			});

			// Summary log
			const summaryParts = [];
			if (uploadResult.successCount > 0) summaryParts.push(`${uploadResult.successCount} uploaded`);
			if (uploadResult.skipCount > 0) summaryParts.push(`${uploadResult.skipCount} skipped`);
			if (uploadResult.errorCount > 0) summaryParts.push(`${uploadResult.errorCount} failed`);

			addLogEntry(
				`🔐 Secure batch complete: ${summaryParts.join(', ')}`,
				uploadResult.errorCount > 0 ? 'warning' : 'success'
			);

			// Reset form and refresh photos
			uploadFiles = [];
			description = '';

			// Clear the file input
			const fileInput = document.getElementById('photo-file') as HTMLInputElement;
			if (fileInput) {
				fileInput.value = '';
			}

			await fetchPhotos();

		} catch (err) {
			console.error('🔐 Error in secure batch upload:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`🔐 Secure batch upload failed: ${errorMessage}`, 'error');
			error = errorMessage;

			// TokenExpiredError is handled automatically by the http client
			if (err instanceof TokenExpiredError) {
				// No need to handle manually, http client already logged out
				return;
			}
		} finally {
			isUploading = false;
			uploadProgress = 0;
		}
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

			// Update app store
			app.update(a => ({
				...a,
				userPhotos: photos
			}));

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

	async function saveSettings() {
		try {
			const settingsData = {
				auto_upload_enabled: autoUploadEnabled
			};

			const response = await http.put('/auth/settings', settingsData);

			if (!response.ok) {
				throw new Error(`Failed to save settings: ${response.status}`);
			}

			// Also update the Android background service setting
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

		} catch (err) {
			console.error('🢄Error saving settings:', err);
			const errorMessage = handleApiError(err);
			addLogEntry(`Settings save failed: ${errorMessage}`, 'error');
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
			myGoto(`/?lat=${photo.latitude}&lon=${photo.longitude}&zoom=18`);
		}
	}

	function goToLogin() {
		navigateWithHistory('/login');
	}
</script>

<div class="photos-container page-scrollable">
    <div class="back-button-container">
        <BackButton fallbackHref="/" title="Back to Map"/>
    </div>

    <header>
        <h1>My Photos</h1>
        {#if TAURI}
            <button class="settings-button" on:click={() => showSettings = !showSettings}>
                <Settings size={20}/>
                Settings
            </button>
        {/if}
    </header>

    {#if error}
        <div class="error-message">{error}</div>
    {/if}

    {#if TAURI && showSettings}
        <div class="settings-panel">
            <h2>Auto-Upload Settings</h2>
            {#if !user}
                <div class="login-notice">
                    <p>Please
                        <button type="button" class="login-link" on:click={goToLogin}>log in</button>
                        to access settings.
                    </p>
                </div>
            {/if}
            <div class="form-group">
                <label>
                    <input type="checkbox" bind:checked={autoUploadEnabled} data-testid="auto-upload-checkbox"
                           disabled={!user}>
                    Enable auto-upload
                </label>
                <p class="help-text">
                    Automatically upload photos taken with the app's camera to your account.
                </p>
            </div>

            <div class="button-group">
                <button class="secondary-button" on:click={() => showSettings = false}>Cancel</button>
                <button class="primary-button" on:click={saveSettings} data-testid="save-settings-button"
                        disabled={!user}>Save Settings
                </button>
            </div>
        </div>
    {/if}

    <div class="upload-section" data-testid="upload-section">
        <h2>Upload Photos</h2>
        {#if !user}
            <div class="login-notice">
                <p>Please
                    <button type="button" class="login-link" on:click={goToLogin}>log in</button>
                    to upload photos.
                </p>
            </div>
        {/if}
        <form on:submit|preventDefault={handleUpload} data-testid="upload-form">
            <div class="form-group">
                <label for="photo-file">Select photos:</label>
                <input
                        type="file"
                        id="photo-file"
                        accept="image/*"
                        multiple
                        data-testid="photo-file-input"
                        disabled={!user}
                        on:change={(e) => {
                        const files = (e.target as HTMLInputElement).files;
                        uploadFiles = files ? Array.from(files) : [];
                    }}
                        required
                />
            </div>

            <div class="form-group">
                <label for="description">Description (optional):</label>
                <textarea
                        id="description"
                        bind:value={description}
                        placeholder="Optional description for this photo"
                        rows="1"
                        class="auto-resize-textarea"
                        disabled={!user}
                        on:input={autoResizeTextarea}
                ></textarea>
            </div>

            <div class="form-group">
                <label>
                    <input type="checkbox" bind:checked={isPublic} disabled={!user}>
                    Make this photo public
                </label>
            </div>

            {#if uploadFiles.length > 0}
                <div class="selected-files">
                    <p>Selected files: {uploadFiles.length}</p>
                    <ul class="file-list">
                        {#each uploadFiles as file}
                            <li class="file-item">{file.name}</li>
                        {/each}
                    </ul>
                </div>
            {/if}

            <button
                    type="submit"
                    class="primary-button"
                    data-testid="upload-submit-button"
                    disabled={!user || !uploadFiles.length || isUploading}
            >
                <Upload size={20}/>
                {#if isUploading}
                    Uploading... ({uploadProgress}%)
                {:else if uploadFiles.length > 1}
                    Upload {uploadFiles.length} Photos
                {:else if uploadFiles.length === 1}
                    Upload Photo
                {:else}
                    Select Photos
                {/if}
            </button>

            {#if isUploading}
                <div class="progress-bar">
                    <div class="progress" style="width: {uploadProgress}%"></div>
                </div>
                <p class="upload-progress">{uploadProgress}% uploaded</p>
            {/if}
        </form>
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
        <h2>My Photos ({photos.length})</h2>

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
                        <div class="photo-image">
                            <details>
                                <summary>?</summary>
                                <pre>{JSON.stringify(photo, null, 2)}</pre>
                            </details>
                            <img
                                    src={photo.thumbnail_url || `${backendUrl}/photos/${photo.id}/thumbnail`}
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
        {/if}
    </div>
</div>

<style>
    .photos-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }

    .back-button-container {
        margin-bottom: 20px;
    }

    header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
    }

    h1 {
        margin: 0;
        color: #333;
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

    .upload-section {
        background-color: white;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        padding: 24px;
        margin-bottom: 32px;
    }

    .form-group {
        margin-bottom: 16px;
    }

    .auto-resize-textarea {
        resize: none;
        min-height: 40px;
        overflow: hidden;
        transition: height 0.2s ease;
    }

    .selected-files {
        margin-bottom: 16px;
        padding: 12px;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
    }

    .selected-files p {
        margin: 0 0 8px 0;
        font-weight: 500;
        color: #374151;
    }

    .file-list {
        margin: 0;
        padding: 0;
        list-style: none;
        max-height: 120px;
        overflow-y: auto;
    }

    .file-item {
        padding: 4px 0;
        font-size: 14px;
        color: #6b7280;
        word-break: break-all;
    }

    label {
        display: block;
        margin-bottom: 8px;
        font-weight: 500;
        color: #555;
    }

    textarea {
        width: 100%;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 16px;
    }

    textarea {
        min-height: 100px;
        resize: vertical;
    }

    input[type="checkbox"] {
        margin-right: 8px;
    }

    .primary-button {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 12px 24px;
        background-color: #4a90e2;
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }

    .primary-button:hover {
        background-color: #3a7bc8;
    }

    .primary-button:disabled {
        background-color: #a0c0e8;
        cursor: not-allowed;
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

    .progress-bar {
        height: 8px;
        background-color: #f0f0f0;
        border-radius: 4px;
        margin-top: 16px;
        overflow: hidden;
    }

    .progress {
        height: 100%;
        background-color: #4a90e2;
        transition: width 0.3s ease;
    }

    .upload-progress {
        margin-top: 8px;
        font-size: 14px;
        color: #666;
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

    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 20px;
    }

    .login-notice {
        background-color: #e3f2fd;
        color: #1565c0;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 16px;
        text-align: center;
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
</style>
