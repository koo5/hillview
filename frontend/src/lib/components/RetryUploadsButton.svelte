<script lang="ts">

	import {autoUploadSettings} from "$lib/autoUploadSettings";
	import {TAURI, BROWSER} from '$lib/tauri.js';
	import {Upload} from 'lucide-svelte';
	import {invoke} from "@tauri-apps/api/core";
	import {fetchPhotoStats} from "$lib/photoStatsAdapter";
	import {uploadManager} from "$lib/browser/uploadManager";

	export let photo: { id: string | number; processing_status?: string, upload_status?: string } = { id: 'global' };
	export let addLogEntry: any = () => {};
	export let global: boolean = false;


	async function manualUpload(photoId: string | number) {
		console.log(`🢄Manual upload requested for photo ${photoId}`);

		try {
			if (TAURI) {
				const result = await invoke('plugin:hillview|cmd', {
					command: 'retry_uploads'
				}) as { success: boolean };
				if (result.success) {
					addLogEntry('Manual upload triggered successfully', 'success');
					setTimeout(() => {
						fetchPhotoStats();
					}, 2000);
				} else {
					addLogEntry('Failed to trigger manual upload', 'error');
				}
			} else if (BROWSER) {
				// Browser: trigger upload manager
				await uploadManager.uploadPending();
				addLogEntry('Manual upload triggered', 'success');
				setTimeout(() => {
					fetchPhotoStats();
				}, 2000);
			} else {
				addLogEntry('Manual upload is not available', 'warning');
			}
		} catch (error) {
			console.error('🢄Error triggering manual upload:', error);
			addLogEntry(`Manual upload failed: ${error}`, 'error');
		}
	}


</script>
{#if (TAURI || BROWSER) && (global || (photo.processing_status && photo.processing_status !== 'completed') || (photo.upload_status && photo.upload_status !== 'completed'))}
	{#if $autoUploadSettings.value?.auto_upload_enabled}
		<button class="action-button upload" data-testid="manual-upload-button"
				data-photo-id={photo.id} on:click={() => manualUpload(photo.id)}>
			<Upload size={16}/>
			Retry/Sync
		</button>
	{:else}
		<span class="help-text">
			Enable auto-upload in settings to retry failed uploads.
		</span>
	{/if}
{/if}
