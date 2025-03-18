<script>
    import { onMount } from 'svelte';
    import { goto } from '$app/navigation';
    import { Upload, Trash2, Map, Settings } from 'lucide-svelte';
    import Spinner from '../../components/Spinner.svelte';
    import { auth } from '$lib/auth.svelte.ts';
    import { app } from '$lib/data.svelte.js';
    import { get } from 'svelte/store';

    let photos = [];
    let isLoading = true;
    let error = null;
    let uploadFile = null;
    let description = '';
    let isPublic = true;
    let isUploading = false;
    let uploadProgress = 0;
    let autoUploadEnabled = false;
    let autoUploadFolder = '';
    let showSettings = false;
    let user = null;

    onMount(async () => {
        // Check if user is authenticated
        auth.subscribe(value => {
            if (!value.isAuthenticated) {
                goto('/login');
                return;
            }
            user = value.user;
            if (user) {
                autoUploadEnabled = user.auto_upload_enabled;
                autoUploadFolder = user.auto_upload_folder || '';
            }
        });

        try {
            // Fetch user photos
            await fetchPhotos();
        } catch (err) {
            console.error('Error loading photos:', err);
            error = err.message;
        } finally {
            isLoading = false;
        }
    });

    async function fetchPhotos() {
        const authValue = get(auth);
        if (!authValue.isAuthenticated || !authValue.token) return;
        
        try {
            const response = await fetch('http://localhost:8089/api/photos', {
                headers: {
                    'Authorization': `Bearer ${authValue.token}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to fetch photos');
            }
            
            photos = await response.json();
            
            // Update app store with user photos
            app.update(a => ({
                ...a,
                userPhotos: photos
            }));
        } catch (err) {
            console.error('Error fetching photos:', err);
            error = err.message;
        }
    }

    async function handleUpload() {
        if (!uploadFile) return;
        
        isUploading = true;
        uploadProgress = 0;
        const authValue = get(auth);
        
        try {
            const formData = new FormData();
            formData.append('file', uploadFile);
            formData.append('description', description);
            formData.append('is_public', isPublic);
            
            const xhr = new XMLHttpRequest();
            
            // Track upload progress
            xhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    uploadProgress = Math.round((event.loaded / event.total) * 100);
                }
            });
            
            // Create a promise to handle the XHR request
            const uploadPromise = new Promise((resolve, reject) => {
                xhr.onload = () => {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(JSON.parse(xhr.responseText));
                    } else {
                        reject(new Error('Upload failed'));
                    }
                };
                xhr.onerror = () => reject(new Error('Network error'));
            });
            
            // Set up and send the request
            xhr.open('POST', 'http://localhost:8089/api/photos/upload');
            xhr.setRequestHeader('Authorization', `Bearer ${authValue.token}`);
            xhr.send(formData);
            
            // Wait for the upload to complete
            const result = await uploadPromise;
            
            // Reset form and refresh photos
            uploadFile = null;
            description = '';
            await fetchPhotos();
            
        } catch (err) {
            console.error('Error uploading photo:', err);
            error = err.message;
        } finally {
            isUploading = false;
        }
    }

    async function deletePhoto(photoId) {
        if (!confirm('Are you sure you want to delete this photo?')) return;
        
        const authValue = get(auth);
        
        try {
            const response = await fetch(`http://localhost:8089/api/photos/${photoId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${authValue.token}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to delete photo');
            }
            
            // Remove the photo from the list
            photos = photos.filter(photo => photo.id !== photoId);
            
            // Update app store
            app.update(a => ({
                ...a,
                userPhotos: photos
            }));
            
        } catch (err) {
            console.error('Error deleting photo:', err);
            error = err.message;
        }
    }

    async function saveSettings() {
        const authValue = get(auth);
        
        try {
            const formData = new FormData();
            formData.append('auto_upload_enabled', autoUploadEnabled);
            if (autoUploadFolder) {
                formData.append('auto_upload_folder', autoUploadFolder);
            }
            
            const response = await fetch('http://localhost:8089/api/auth/settings', {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${authValue.token}`
                },
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('Failed to save settings');
            }
            
            showSettings = false;
            
        } catch (err) {
            console.error('Error saving settings:', err);
            error = err.message;
        }
    }

    function formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString();
    }

    function viewOnMap(photo) {
        if (photo.latitude && photo.longitude) {
            goto(`/?lat=${photo.latitude}&lon=${photo.longitude}&zoom=18`);
        }
    }
</script>

<div class="photos-container">
    <header>
        <h1>My Photos</h1>
        <button class="settings-button" on:click={() => showSettings = !showSettings}>
            <Settings size={20} />
            Settings
        </button>
    </header>
    
    {#if error}
        <div class="error-message">{error}</div>
    {/if}
    
    {#if showSettings}
        <div class="settings-panel">
            <h2>Auto-Upload Settings</h2>
            <div class="form-group">
                <label>
                    <input type="checkbox" bind:checked={autoUploadEnabled}>
                    Enable auto-upload
                </label>
            </div>
            
            {#if autoUploadEnabled}
                <div class="form-group">
                    <label for="auto-upload-folder">Auto-upload folder path:</label>
                    <input 
                        type="text" 
                        id="auto-upload-folder" 
                        bind:value={autoUploadFolder} 
                        placeholder="Enter folder path"
                    />
                    <p class="help-text">
                        This setting is primarily for desktop and mobile apps. 
                        The app will monitor this folder and automatically upload new photos.
                    </p>
                </div>
            {/if}
            
            <div class="button-group">
                <button class="secondary-button" on:click={() => showSettings = false}>Cancel</button>
                <button class="primary-button" on:click={saveSettings}>Save Settings</button>
            </div>
        </div>
    {/if}
    
    <div class="upload-section">
        <h2>Upload New Photo</h2>
        <form on:submit|preventDefault={handleUpload}>
            <div class="form-group">
                <label for="photo-file">Select photo:</label>
                <input 
                    type="file" 
                    id="photo-file" 
                    accept="image/*" 
                    bind:files={e => uploadFile = e[0]} 
                    required
                />
            </div>
            
            <div class="form-group">
                <label for="description">Description (optional):</label>
                <textarea 
                    id="description" 
                    bind:value={description} 
                    placeholder="Enter a description for this photo"
                ></textarea>
            </div>
            
            <div class="form-group">
                <label>
                    <input type="checkbox" bind:checked={isPublic}>
                    Make this photo public
                </label>
            </div>
            
            <button 
                type="submit" 
                class="primary-button" 
                disabled={isUploading || !uploadFile}
            >
                <Upload size={20} />
                {isUploading ? 'Uploading...' : 'Upload Photo'}
            </button>
            
            {#if isUploading}
                <div class="progress-bar">
                    <div class="progress" style="width: {uploadProgress}%"></div>
                </div>
                <p class="upload-progress">{uploadProgress}% uploaded</p>
            {/if}
        </form>
    </div>
    
    <div class="photos-grid">
        <h2>My Photos ({photos.length})</h2>
        
        {#if isLoading}
            <div class="loading-container">
                <Spinner />
                <p>Loading your photos...</p>
            </div>
        {:else if photos.length === 0}
            <p class="no-photos">You haven't uploaded any photos yet.</p>
        {:else}
            <div class="grid">
                {#each photos as photo (photo.id)}
                    <div class="photo-card">
                        <div class="photo-image">
                            <img 
                                src={photo.thumbnail_url || `http://localhost:8089/api/photos/${photo.id}/thumbnail`} 
                                alt={photo.description || photo.filename} 
                            />
                        </div>
                        <div class="photo-info">
                            <h3>{photo.filename}</h3>
                            {#if photo.description}
                                <p class="description">{photo.description}</p>
                            {/if}
                            <p class="meta">Uploaded: {formatDate(photo.uploaded_at)}</p>
                            {#if photo.captured_at}
                                <p class="meta">Captured: {formatDate(photo.captured_at)}</p>
                            {/if}
                            <div class="photo-actions">
                                {#if photo.latitude && photo.longitude}
                                    <button class="action-button" on:click={() => viewOnMap(photo)}>
                                        <Map size={16} />
                                        View on Map
                                    </button>
                                {/if}
                                <button class="action-button delete" on:click={() => deletePhoto(photo.id)}>
                                    <Trash2 size={16} />
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
    
    label {
        display: block;
        margin-bottom: 8px;
        font-weight: 500;
        color: #555;
    }
    
    input[type="text"],
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
