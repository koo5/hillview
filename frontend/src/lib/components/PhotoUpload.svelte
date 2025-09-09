<script lang="ts">
	import {Upload} from 'lucide-svelte';
	import {secureUploadFiles} from '$lib/secureUpload';
	import {handleApiError, TokenExpiredError} from '$lib/http';
	import type {User} from '$lib/auth.svelte';

	export let user: User | null = null;
	export let onLogEntry: (message: string, type: 'success' | 'warning' | 'error' | 'info') => void = () => {};
	export let onUploadComplete: () => void = () => {};
	export let goToLogin: () => void = () => {};

	let uploadFiles: File[] = [];
	let description = '';
	let isPublic = true;
	let isUploading = false;
	let uploadProgress = 0;

	function autoResizeTextarea(event: Event) {
		const textarea = event.target as HTMLTextAreaElement;
		textarea.style.height = 'auto';
		textarea.style.height = `${textarea.scrollHeight}px`;
	}

	async function handleUpload() {
		console.log('🢄handleUpload');

		if (!uploadFiles.length) return;

		isUploading = true;
		uploadProgress = 0;

		const totalFiles = uploadFiles.length;
		onLogEntry(`Starting secure batch upload: ${totalFiles} file${totalFiles > 1 ? 's' : ''}`, 'info');

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
						onLogEntry(`Uploading ${completed + 1}/${total}: ${currentFile}`, 'info');
					}
				}
			);

			// Process results
			uploadResult.results.forEach((result, index) => {
				const file = uploadFiles[index];
				if (result.success) {
					onLogEntry(`✅ Uploaded: ${file.name}`, 'success');
				} else {
					onLogEntry(`❌ Failed: ${file.name} - ${result.error}`, 'error');
				}
			});

			// Summary log
			const summaryParts = [];
			if (uploadResult.successCount > 0) summaryParts.push(`${uploadResult.successCount} uploaded`);
			if (uploadResult.skipCount > 0) summaryParts.push(`${uploadResult.skipCount} skipped`);
			if (uploadResult.errorCount > 0) summaryParts.push(`${uploadResult.errorCount} failed`);

			onLogEntry(
				`🔐 Secure batch complete: ${summaryParts.join(', ')}`,
				uploadResult.errorCount > 0 ? 'warning' : 'success'
			);

			// Reset form
			uploadFiles = [];
			description = '';

			// Clear the file input
			const fileInput = document.getElementById('photo-file') as HTMLInputElement;
			if (fileInput) {
				fileInput.value = '';
			}

			// Notify parent to refresh photos
			onUploadComplete();

		} catch (err) {
			console.error('🔐 Error in secure batch upload:', err);
			const errorMessage = handleApiError(err);
			onLogEntry(`🔐 Secure batch upload failed: ${errorMessage}`, 'error');

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
</script>

<div class="upload-section" data-testid="upload-section">
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
			<label for="photo-file">Select photos to upload:</label>
			<input
				type="file"
				id="photo-file"
				accept="image/*"
				multiple
				data-testid="photo-file-input"
				disabled={!user || isUploading}
				on:change={(e) => {
					console.log('🢄 File input changed');
					const files = (e.target as HTMLInputElement).files;
					console.log(`🢄 Selected ${files?.length || 0} files`);
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

<style>
	.upload-section {
		padding: 0;
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
</style>
