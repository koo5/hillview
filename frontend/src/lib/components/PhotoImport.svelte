<script lang="ts">
	import { invoke } from '@tauri-apps/api/core';
	import { FolderOpen } from 'lucide-svelte';
	import Spinner from '../../components/Spinner.svelte';

	export let onImportComplete: (importedCount: number) => void = () => {};
	export let onLogEntry: (message: string, type: 'success' | 'warning' | 'error' | 'info') => void = () => {};

	let isImporting = false;

	interface ImportResult {
		success: boolean;
		imported_count: number;
		failed_count?: number;
		failed_files?: string[];
		import_errors?: string[];
		error?: string;
	}

	async function handleImportPhotos() {
		if (isImporting) return;
		
		try {
			isImporting = true;
			onLogEntry('Opening file picker...', 'info');
			
			const result = await invoke('plugin:hillview|import_photos') as ImportResult;
			console.log('📂 Import result:', result);
			
			if (result.success || result.imported_count > 0) {
				const importedCount = result.imported_count || 0;
				const failedCount = result.failed_count || 0;
				
				if (importedCount > 0) {
					let message = `✅ Successfully imported ${importedCount} photo${importedCount > 1 ? 's' : ''}`;
					if (failedCount > 0) {
						message += `, ${failedCount} failed`;
					}
					onLogEntry(message, 'success');
					
					// Show details of any failures
					if (result.import_errors && result.import_errors.length > 0) {
						result.import_errors.forEach((errorMsg: string, index: number) => {
							if (index < 3) { // Limit to first 3 errors to avoid spam
								onLogEntry(`⚠️ ${errorMsg}`, 'warning');
							}
						});
						if (result.import_errors.length > 3) {
							onLogEntry(`⚠️ ...and ${result.import_errors.length - 3} more errors`, 'warning');
						}
					}
					
					// Notify parent component to refresh photos
					onImportComplete(importedCount);
				} else if (failedCount > 0) {
					onLogEntry(`❌ All ${failedCount} files failed to import`, 'error');
					
					// Show specific failure reasons
					if (result.import_errors && result.import_errors.length > 0) {
						result.import_errors.forEach((errorMsg: string, index: number) => {
							if (index < 5) { // Show more errors when everything failed
								onLogEntry(`• ${errorMsg}`, 'error');
							}
						});
						if (result.import_errors.length > 5) {
							onLogEntry(`• ...and ${result.import_errors.length - 5} more errors`, 'error');
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
			console.error('🢄Error importing photos:', err);
			const errorMessage = err instanceof Error ? err.message : String(err);
			onLogEntry(`❌ Import error: ${errorMessage}`, 'error');
		} finally {
			isImporting = false;
		}
	}
</script>

<div class="photo-import">
	<button 
		class="import-button"
		disabled={isImporting}
		on:click={handleImportPhotos}
	>
		<FolderOpen size={20}/>
		{#if isImporting}
			Importing...
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
	.photo-import {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		align-items: flex-start;
	}

	.import-button {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		background: var(--primary-color);
		color: white;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.9rem;
		font-weight: 500;
		transition: all 0.2s ease;
	}

	.import-button:hover:not(:disabled) {
		background: var(--primary-hover);
		transform: translateY(-1px);
	}

	.import-button:disabled {
		background: var(--gray-400);
		cursor: not-allowed;
		transform: none;
	}

	.importing-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem;
		background: var(--background-secondary);
		border-radius: 6px;
		font-size: 0.85rem;
		color: var(--text-secondary);
	}
</style>