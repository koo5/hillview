<script lang="ts">
	import { invoke } from '@tauri-apps/api/core';
	import { FolderOpen } from 'lucide-svelte';
	import Spinner from './Spinner.svelte';
	import type {User} from '$lib/auth.svelte';

	export let user: User | null = null;
	export let onImportComplete: (importedCount: number) => void = () => {};
	export let onLogEntry: (message: string, type: 'success' | 'warning' | 'error' | 'info') => void = () => {};
	export let goToLogin: () => void = () => {};

	let isImporting = false;

	interface ImportResult {
		success: boolean;
		selectedFiles: string[];
		importedCount: number;
		failedCount?: number;
		failedFiles?: string[];
		importErrors?: string[];
		error?: string;
	}

	async function handleImportFromDevice() {
		if (isImporting || !user) return;

		try {
			isImporting = true;
			onLogEntry('Opening device file picker...', 'info');

			const result = await invoke('plugin:hillview|import_photos') as ImportResult;
			console.log('🢄📂 Import result:', result);

			if (result.success || result.importedCount > 0) {
				const importedCount = result.importedCount || 0;
				const failedCount = result.failedCount || 0;

				if (importedCount > 0) {
					let message = `✅ Successfully selected ${importedCount} photo${importedCount > 1 ? 's' : ''} from device`;
					if (failedCount > 0) {
						message += `, ${failedCount} failed`;
					}
					onLogEntry(message, 'success');

					// Show details of any failures
					if (result.importErrors && result.importErrors.length > 0) {
						result.importErrors.forEach((errorMsg: string, index: number) => {
							if (index < 3) { // Limit to first 3 errors to avoid spam
								onLogEntry(`⚠️ ${errorMsg}`, 'warning');
							}
						});
						if (result.importErrors.length > 3) {
							onLogEntry(`⚠️ ...and ${result.importErrors.length - 3} more errors`, 'warning');
						}
					}

					// Notify parent component to refresh photos
					onImportComplete(importedCount);
				} else if (failedCount > 0) {
					onLogEntry(`❌ All ${failedCount} files failed to import`, 'error');

					// Show specific failure reasons
					if (result.importErrors && result.importErrors.length > 0) {
						result.importErrors.forEach((errorMsg: string, index: number) => {
							if (index < 5) { // Show more errors when everything failed
								onLogEntry(`• ${errorMsg}`, 'error');
							}
						});
						if (result.importErrors.length > 5) {
							onLogEntry(`• ...and ${result.importErrors.length - 5} more errors`, 'error');
						}
					}
				} else {
					onLogEntry('No files were selected for import', 'info');
				}
			} else {
				const errorMsg = result.error || 'Import failed';
				onLogEntry(`❌ Import failed: ${errorMsg}`, 'error');
			}

		} catch (err) {
			console.error('🢄Error importing photos from device:', err);
			const errorMessage = err instanceof Error ? err.message : String(err);
			onLogEntry(`❌ Device import error: ${errorMessage}`, 'error');
		} finally {
			isImporting = false;
		}
	}
</script>

<div class="photo-import-device">
	{#if !user}
		<div class="login-notice">
			<p>Please
				<button type="button" class="login-link" on:click={goToLogin}>log in</button>
				to import photos from your device.
			</p>
		</div>
	{/if}

	<div class="import-description">
		<p>Import existing photos from your device gallery or file system. The app will open your device's file picker to select photos.</p>
	</div>

	<button
		class="import-button"
		disabled={isImporting || !user}
		on:click={handleImportFromDevice}
		data-testid="import-from-device-button"
	>
		<FolderOpen size={20}/>
		{#if isImporting}
			Selecting Photos...
		{:else}
			Import from Device
		{/if}
	</button>

	{#if isImporting}
		<div class="importing-status">
			<Spinner />
			<span>Opening file picker...</span>
		</div>
	{/if}
</div>

<style>
	.photo-import-device {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.import-description {
		color: #6c757d;
		font-size: 14px;
		line-height: 1.4;
	}

	.import-description p {
		margin: 0;
	}

	.import-button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		background: var(--primary-color, #4a90e2);
		color: white;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: all 0.2s ease;
		align-self: flex-start;
	}

	.import-button:hover:not(:disabled) {
		background: var(--primary-hover, #3a7bc8);
		transform: translateY(-1px);
	}

	.import-button:disabled {
		background: #a0c0e8;
		cursor: not-allowed;
		transform: none;
	}

	.importing-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem;
		background: var(--background-secondary, #f8f9fa);
		border-radius: 6px;
		font-size: 0.85rem;
		color: var(--text-secondary, #6c757d);
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
