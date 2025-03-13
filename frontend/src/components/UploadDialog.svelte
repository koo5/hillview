<script>
    import { createEventDispatcher } from 'svelte';
    import { Upload, X, Image, MapPin, Compass, Info } from 'lucide-svelte';
    import { auth, debugAuth } from '$lib/auth.svelte.ts';
    import { get } from 'svelte/store';
    import { app } from '$lib/data.svelte.js';

    export let show = false;
    
    // Subscribe to auth store
    let isAuthenticated = false;
    let authToken = null;
    
    auth.subscribe(value => {
        isAuthenticated = value.isAuthenticated;
        authToken = value.token;
        
        // Debug auth state when dialog is shown
        if (show) {
            console.log('UploadDialog auth state:', debugAuth());
        }
    });
    
    const dispatch = createEventDispatcher();
    
    let files = [];
    let isUploading = false;
    let uploadProgress = 0;
    let description = '';
    let isPublic = true;
    let error = null;
    let success = null;
    
    // Reset form when dialog is opened
    $: if (show) {
        resetForm();
    }
    
    function resetForm() {
        files = [];
        description = '';
        isPublic = true;
        error = null;
        success = null;
        uploadProgress = 0;
    }
    
    function close() {
        if (isUploading) return;
        resetForm();
        dispatch('close');
    }
    
    function handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }
    
    function handleDrop(e) {
        e.preventDefault();
        if (isUploading) return;
        
        const droppedFiles = Array.from(e.dataTransfer.files);
        handleFiles(droppedFiles);
    }
    
    function handleFileInput(e) {
        if (isUploading) return;
        const selectedFiles = Array.from(e.target.files);
        handleFiles(selectedFiles);
    }
    
    function handleFiles(newFiles) {
        // Filter for image files
        const imageFiles = newFiles.filter(file => file.type.startsWith('image/'));
        
        if (imageFiles.length === 0) {
            error = 'Please select image files only';
            return;
        }
        
        files = imageFiles;
        error = null;
    }
    
    function removeFile(index) {
        if (isUploading) return;
        files = files.filter((_, i) => i !== index);
    }
    
    async function handleUpload() {
        if (files.length === 0) {
            error = 'Please select at least one file to upload';
            return;
        }
        
        isUploading = true;
        error = null;
        success = null;
        
        if (!isAuthenticated || !authToken) {
            error = 'You must be logged in to upload photos';
            isUploading = false;
            
            // Show login button
            setTimeout(() => {
                if (confirm('Would you like to log in now?')) {
                    window.location.href = '/login';
                }
            }, 500);
            
            return;
        }
        
        try {
            // Upload each file
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                uploadProgress = Math.round((i / files.length) * 100);
                
                const formData = new FormData();
                formData.append('file', file);
                formData.append('description', description);
                formData.append('is_public', isPublic);
                
                const xhr = new XMLHttpRequest();
                
                // Create a promise to handle the XHR request
                const uploadPromise = new Promise((resolve, reject) => {
                    xhr.onload = () => {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            resolve(JSON.parse(xhr.responseText));
                        } else {
                            reject(new Error(`Upload failed: ${xhr.statusText}`));
                        }
                    };
                    xhr.onerror = () => reject(new Error('Network error during upload'));
                    
                    // Track individual file upload progress
                    xhr.upload.addEventListener('progress', (event) => {
                        if (event.lengthComputable) {
                            const fileProgress = Math.round((event.loaded / event.total) * 100);
                            // Calculate overall progress: completed files + current file progress
                            uploadProgress = Math.round((i / files.length) * 100 + (fileProgress / files.length));
                        }
                    });
                });
                
                // Set up and send the request
                xhr.open('POST', 'http://localhost:8089/api/photos/upload');
                xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);
                xhr.send(formData);
                
                // Wait for the upload to complete
                await uploadPromise;
            }
            
            uploadProgress = 100;
            success = `Successfully uploaded ${files.length} photo${files.length > 1 ? 's' : ''}`;
            
            // Reset form after a short delay
            setTimeout(() => {
                resetForm();
                dispatch('uploaded');
            }, 2000);
            
        } catch (err) {
            console.error('Error uploading photos:', err);
            error = err.message || 'Failed to upload photos';
        } finally {
            isUploading = false;
        }
    }
</script>

{#if show}
<div class="upload-dialog-backdrop" on:click={close}>
    <div class="upload-dialog" on:click|stopPropagation>
        <div class="upload-dialog-header">
            <h2>Upload Photos</h2>
            <button class="close-button" on:click={close} disabled={isUploading}>
                <X size={24} />
            </button>
        </div>
        
        <div class="upload-dialog-content">
            {#if error}
                <div class="error-message">{error}</div>
            {/if}
            
            {#if success}
                <div class="success-message">{success}</div>
            {/if}
            
            <!-- Debug info -->
            {#if $app.debug > 0}
                <div class="debug-info">
                    <h4>Auth Debug Info:</h4>
                    <pre>isAuthenticated: {get(auth).isAuthenticated}</pre>
                    <pre>token: {get(auth).token ? 'exists' : 'none'}</pre>
                    <pre>tokenExpires: {get(auth).tokenExpires}</pre>
                    <pre>user: {get(auth).user ? JSON.stringify(get(auth).user, null, 2) : 'none'}</pre>
                </div>
            {/if}
            
            {#if !isAuthenticated}
                <div class="login-prompt">
                    <h3>Login Required</h3>
                    <p>You need to be logged in to upload photos.</p>
                    <div class="button-group">
                        <a href="/login" class="primary-button">Login</a>
                        <a href="/login" class="secondary-button">Register</a>
                    </div>
                </div>
            {:else if files.length === 0}
                <div 
                    class="drop-area"
                    on:dragover={handleDragOver}
                    on:drop={handleDrop}
                >
                    <div class="drop-area-content">
                        <Upload size={48} />
                        <p>Drag photos here or click to browse</p>
                        <input 
                            type="file" 
                            id="file-input" 
                            accept="image/*" 
                            multiple 
                            on:change={handleFileInput}
                        />
                        <button class="browse-button" on:click={() => document.getElementById('file-input').click()}>
                            Browse Files
                        </button>
                    </div>
                </div>
            {:else}
                <div class="selected-files">
                    <h3>Selected Photos ({files.length})</h3>
                    <div class="file-list">
                        {#each files as file, i}
                            <div class="file-item">
                                <div class="file-preview">
                                    <img src={URL.createObjectURL(file)} alt={file.name} />
                                </div>
                                <div class="file-info">
                                    <span class="file-name">{file.name}</span>
                                    <span class="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                                </div>
                                <button class="remove-file" on:click={() => removeFile(i)} disabled={isUploading}>
                                    <X size={16} />
                                </button>
                            </div>
                        {/each}
                    </div>
                    
                    <div class="upload-options">
                        <div class="form-group">
                            <label for="description">
                                <Info size={16} />
                                Description (optional)
                            </label>
                            <textarea 
                                id="description" 
                                bind:value={description} 
                                placeholder="Enter a description for these photos"
                                disabled={isUploading}
                            ></textarea>
                        </div>
                        
                        <div class="form-group checkbox">
                            <label>
                                <input type="checkbox" bind:checked={isPublic} disabled={isUploading}>
                                <MapPin size={16} />
                                Make photos public on the map
                            </label>
                        </div>
                        
                        <div class="form-info">
                            <p>
                                <Compass size={16} />
                                Photos with GPS and compass data will be automatically placed on the map.
                            </p>
                        </div>
                    </div>
                </div>
            {/if}
        </div>
        
        <div class="upload-dialog-footer">
            {#if isUploading}
                <div class="progress-container">
                    <div class="progress-bar">
                        <div class="progress" style="width: {uploadProgress}%"></div>
                    </div>
                    <span class="progress-text">{uploadProgress}% uploaded</span>
                </div>
            {/if}
            
            <div class="button-group">
                <button class="cancel-button" on:click={close} disabled={isUploading}>
                    Cancel
                </button>
                
                {#if files.length > 0}
                    <button class="upload-button" on:click={handleUpload} disabled={isUploading}>
                        {#if isUploading}
                            Uploading...
                        {:else}
                            <Upload size={16} />
                            Upload {files.length} Photo{files.length > 1 ? 's' : ''}
                        {/if}
                    </button>
                {/if}
            </div>
        </div>
    </div>
</div>
{/if}

<style>
    .upload-dialog-backdrop {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
    
    .upload-dialog {
        background-color: white;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        width: 90%;
        max-width: 600px;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }
    
    .upload-dialog-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 20px;
        border-bottom: 1px solid #eee;
    }
    
    .upload-dialog-header h2 {
        margin: 0;
        font-size: 1.5rem;
        color: #333;
    }
    
    .close-button {
        background: none;
        border: none;
        color: #666;
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .close-button:hover {
        background-color: #f5f5f5;
        color: #333;
    }
    
    .upload-dialog-content {
        padding: 20px;
        overflow-y: auto;
        flex: 1;
    }
    
    .drop-area {
        border: 2px dashed #ccc;
        border-radius: 8px;
        padding: 40px 20px;
        text-align: center;
        cursor: pointer;
        transition: border-color 0.3s, background-color 0.3s;
    }
    
    .drop-area:hover {
        border-color: #4a90e2;
        background-color: #f8f9ff;
    }
    
    .drop-area-content {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 16px;
        color: #666;
    }
    
    .drop-area-content svg {
        color: #4a90e2;
    }
    
    input[type="file"] {
        display: none;
    }
    
    .browse-button {
        background-color: #4a90e2;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 10px 20px;
        font-size: 16px;
        cursor: pointer;
        transition: background-color 0.3s;
    }
    
    .browse-button:hover {
        background-color: #3a7bc8;
    }
    
    .selected-files {
        display: flex;
        flex-direction: column;
        gap: 20px;
    }
    
    .selected-files h3 {
        margin: 0;
        color: #333;
    }
    
    .file-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
        max-height: 200px;
        overflow-y: auto;
        padding-right: 8px;
    }
    
    .file-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px;
        border: 1px solid #eee;
        border-radius: 4px;
        background-color: #f9f9f9;
    }
    
    .file-preview {
        width: 60px;
        height: 60px;
        border-radius: 4px;
        overflow: hidden;
        flex-shrink: 0;
    }
    
    .file-preview img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    
    .file-info {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 4px;
        overflow: hidden;
    }
    
    .file-name {
        font-weight: 500;
        color: #333;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .file-size {
        font-size: 0.85rem;
        color: #666;
    }
    
    .remove-file {
        background: none;
        border: none;
        color: #666;
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .remove-file:hover {
        background-color: #f0f0f0;
        color: #e53935;
    }
    
    .upload-options {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }
    
    .form-group {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    
    .form-group label {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 500;
        color: #555;
    }
    
    .form-group.checkbox label {
        flex-direction: row;
        align-items: center;
        cursor: pointer;
    }
    
    textarea {
        width: 100%;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
        resize: vertical;
        min-height: 80px;
    }
    
    .form-info {
        background-color: #f5f5f5;
        border-radius: 4px;
        padding: 12px;
    }
    
    .form-info p {
        margin: 0;
        font-size: 14px;
        color: #666;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .upload-dialog-footer {
        padding: 16px 20px;
        border-top: 1px solid #eee;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    
    .progress-container {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    
    .progress-bar {
        height: 8px;
        background-color: #f0f0f0;
        border-radius: 4px;
        overflow: hidden;
    }
    
    .progress {
        height: 100%;
        background-color: #4a90e2;
        transition: width 0.3s ease;
    }
    
    .progress-text {
        font-size: 14px;
        color: #666;
        text-align: right;
    }
    
    .button-group {
        display: flex;
        justify-content: flex-end;
        gap: 12px;
    }
    
    .cancel-button {
        padding: 10px 16px;
        background-color: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
        cursor: pointer;
        transition: background-color 0.3s;
    }
    
    .cancel-button:hover {
        background-color: #e5e5e5;
    }
    
    .upload-button {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 10px 16px;
        background-color: #4a90e2;
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.3s;
    }
    
    .upload-button:hover {
        background-color: #3a7bc8;
    }
    
    .upload-button:disabled,
    .cancel-button:disabled,
    .remove-file:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }
    
    .error-message {
        background-color: #ffebee;
        color: #c62828;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 16px;
    }
    
    .success-message {
        background-color: #e8f5e9;
        color: #2e7d32;
        padding: 12px;
        border-radius: 4px;
        margin-bottom: 16px;
    }
    
    .login-prompt {
        text-align: center;
        padding: 30px 20px;
    }
    
    .login-prompt h3 {
        margin-top: 0;
        margin-bottom: 16px;
        color: #333;
    }
    
    .login-prompt p {
        margin-bottom: 24px;
        color: #666;
    }
    
    .login-prompt .button-group {
        display: flex;
        gap: 12px;
        justify-content: center;
    }
    
    .login-prompt .primary-button,
    .login-prompt .secondary-button {
        display: inline-block;
        text-decoration: none;
        padding: 12px 24px;
        border-radius: 4px;
        font-weight: 500;
    }
    
    .login-prompt .primary-button {
        background-color: #4a90e2;
        color: white;
    }
    
    .login-prompt .secondary-button {
        background-color: #f5f5f5;
        color: #333;
        border: 1px solid #ddd;
    }
    
    .debug-info {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 4px;
        padding: 10px;
        margin-bottom: 16px;
        font-family: monospace;
        font-size: 12px;
    }
    
    .debug-info h4 {
        margin-top: 0;
        margin-bottom: 8px;
        color: #495057;
    }
    
    .debug-info pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-all;
    }
    
    /* Responsive adjustments */
    @media (max-width: 480px) {
        .upload-dialog {
            width: 95%;
            max-height: 95vh;
        }
        
        .upload-dialog-header h2 {
            font-size: 1.2rem;
        }
        
        .drop-area {
            padding: 20px 10px;
        }
        
        .button-group {
            flex-direction: column;
        }
        
        .cancel-button,
        .upload-button {
            width: 100%;
        }
    }
</style>
