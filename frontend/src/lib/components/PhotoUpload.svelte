<script lang="ts">
	import {Upload, FileImage} from 'lucide-svelte';
	import {secureUploadFiles, NonRetryableUploadError, RetryableUploadError} from '$lib/secureUpload';
	import {handleApiError, TokenExpiredError} from '$lib/http';
	import {showNetworkError, removeAlertsBySource} from '$lib/alertSystem.svelte';
	import type {User} from '$lib/auth.svelte';
	import type { LogEntryCallback } from '$lib/types/activityLog';
	import { TAURI_MOBILE } from '$lib/tauri';
	import { invoke } from '@tauri-apps/api/core';

	export let user: User | null = null;
	export let onLogEntry: LogEntryCallback = () => {};
	export let onUploadComplete: () => void = () => {};
	export let goToLogin: () => void = () => {};
	export let disabled = false;

	let uploadFiles: File[] = [];
	let description = '';
	let isPublic = true;
	let isUploading = false;
	let uploadProgress = 0;
	let isSelectingFiles = false;

	interface ImportResult {
		success: boolean;
		selected_files: string[];
		imported_count: number;
		error?: string;
	}

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
		onLogEntry(`Starting upload: ${totalFiles} file${totalFiles > 1 ? 's' : ''}`, 'info', {
			operation: 'upload',
			outcome: 'complete'
		});

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
				},
				(file, errorMessage) => {
					// Immediate feedback when individual files fail
					showNetworkError(`Failed to upload ${file.name}: ${errorMessage}`, 'photo-upload');
					onLogEntry(`❌ Failed: ${file.name} - ${errorMessage}`, 'error', {
						operation: 'upload',
						filename: file.name,
						outcome: 'failure'
					});
				}
			);

			// Process results
			uploadResult.results.forEach((result, index) => {
				const file = uploadFiles[index];
				if (result.success) {
					onLogEntry(`✅ Uploaded: ${file.name}`, 'success', {
						operation: 'upload',
						filename: file.name,
						photo_id: result.photo_id, // Using correct property name
						outcome: 'success'
					});
				} else {
					onLogEntry(`❌ Failed: ${file.name} - ${result.error}`, 'error', {
						operation: 'upload',
						filename: file.name,
						outcome: 'failure'
					});
				}
			});

			// Summary log
			const summaryParts = [];
			if (uploadResult.successCount > 0) summaryParts.push(`${uploadResult.successCount} uploaded`);
			if (uploadResult.skipCount > 0) summaryParts.push(`${uploadResult.skipCount} skipped`);
			if (uploadResult.errorCount > 0) summaryParts.push(`${uploadResult.errorCount} failed`);

			onLogEntry(
				`Batch complete: ${summaryParts.join(', ')}`,
				uploadResult.errorCount > 0 ? 'warning' : 'success',
				{
					operation: 'batch_complete',
					outcome: uploadResult.errorCount > 0 ? 'failure' : 'success'
				}
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
			console.error('🢄Error in batch upload:', err);

			// Clear any previous upload alerts first
			removeAlertsBySource('photo-upload');

			// Handle different error types with appropriate feedback
			if (err instanceof TokenExpiredError) {
				// TokenExpiredError is handled automatically by the http client
				// No need to handle manually, http client already logged out
				return;
			} else if (err instanceof NonRetryableUploadError) {
				// Client-side errors (duplicates, validation, auth issues)
				onLogEntry(`Upload failed: ${err.message}`, 'error');
			} else if (err instanceof RetryableUploadError) {
				// Network/server errors that were retried but still failed
				showNetworkError(
					`Upload failed after retries: ${err.message}. Check your connection and try again.`,
					'photo-upload'
				);
				onLogEntry(`Connection failed: ${err.message}`, 'error');
			} else {
				// Fallback for any other error types
				const errorMessage = handleApiError(err);
				showNetworkError(`Upload failed: ${errorMessage}`, 'photo-upload');
				onLogEntry(`Batch upload failed: ${errorMessage}`, 'error');
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
			<!-- Hidden file input -->
			<input
				type="file"
				id="photo-file"
				accept="image/*"
				multiple
				data-testid="photo-file-input"
				disabled={!user || isUploading || disabled}
				on:change={(e) => {
					console.log('🢄 File input changed');
					const files = (e.target as HTMLInputElement).files;
					console.log(`🢄 Selected ${files?.length || 0} files`);
					uploadFiles = files ? Array.from(files) : [];
				}}
				required
				style="display: none;"
			/>
			<!-- Custom file selection button -->
			<button
				type="button"
				class="file-select-button"
				data-testid="choose-files-button"
				disabled={!user || isUploading || disabled}
				aria-label="Choose photo files to upload"
				on:click={() => {
					const fileInput = document.getElementById('photo-file') as HTMLInputElement;
					if (fileInput) {
						fileInput.click();
					}
				}}
				on:keydown={(e) => {
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						const fileInput = document.getElementById('photo-file') as HTMLInputElement;
						if (fileInput) {
							fileInput.click();
						}
					}
				}}
			>
				<FileImage size={20} />
				Choose Files
			</button>
		</div>

		<div class="form-group">
			<label for="description">Description (optional):</label>
			<textarea
				id="description"
				bind:value={description}
				placeholder="Optional description"
				rows="1"
				class="auto-resize-textarea"
				disabled={!user || disabled}
				on:input={autoResizeTextarea}
			></textarea>
		</div>

<!--		<div class="form-group">-->
<!--			<label>-->
<!--				<input type="checkbox" bind:checked={isPublic} disabled={!user}>-->
<!--				Make these photos public-->
<!--			</label>-->
<!--		</div>-->

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
			disabled={!user || !uploadFiles.length || isUploading || disabled}
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

	.file-select-button {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 12px 20px;
		background-color: #f8fafc;
		color: #374151;
		border: 2px solid #d1d5db;
		border-radius: 6px;
		font-size: 16px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s ease;
		min-height: 48px; /* Ensure good touch target size */
		min-width: 140px;
		touch-action: manipulation; /* Prevent zoom on touch */
	}

	.file-select-button:hover:not(:disabled) {
		background-color: #f1f5f9;
		border-color: #9ca3af;
		transform: translateY(-1px);
	}

	.file-select-button:active {
		transform: translateY(0);
		background-color: #e2e8f0;
	}

	.file-select-button:disabled {
		background-color: #f9fafb;
		color: #9ca3af;
		border-color: #e5e7eb;
		cursor: not-allowed;
		transform: none;
	}

	/* Ensure adequate spacing on mobile */
	@media (max-width: 640px) {
		.file-select-button {
			width: 100%;
			min-height: 52px;
			font-size: 18px;
		}
	}
</style>
