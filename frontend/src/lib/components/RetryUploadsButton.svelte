<script lang="ts">

	import {autoUploadSettings} from "$lib/autoUploadSettings";
	import {TAURI} from '$lib/tauri.js';
	import {Upload} from 'lucide-svelte';
	import {invoke} from "@tauri-apps/api/core";
	import {fetchDevicePhotoStats} from "$lib/devicePhotoStats";

	export let photo: { id: string | number; processing_status?: string, upload_status?: string } = { id: 'global' };
	export let addLogEntry: any = () => {};
	export let global: boolean = false;


	async function manualUpload(photoId: string | number) {
		console.log(`🢄Manual upload requested for photo ${photoId}`);

		try {
			if (TAURI) {
				const result = await invoke('plugin:hillview|retry_failed_uploads') as { success: boolean };
				if (result.success) {
					addLogEntry('Manual upload triggered successfully', 'success');
					setTimeout(() => {
						fetchDevicePhotoStats();
					}, 2000);
				} else {
					addLogEntry('Failed to trigger manual upload', 'error');
				}
			} else {
				addLogEntry('Manual upload is only available on mobile', 'warning');
			}
		} catch (error) {
			console.error('🢄Error triggering manual upload:', error);
			addLogEntry(`Manual upload failed: ${error}`, 'error');
		}
	}


</script>
{#if TAURI && (global || (photo.processing_status && photo.processing_status !== 'completed') || (photo.upload_status && photo.upload_status !== 'completed'))}
	{#if $autoUploadSettings.value?.auto_upload_enabled}
		<button class="action-button upload" data-testid="manual-upload-button"
				data-photo-id={photo.id} on:click={() => manualUpload(photo.id)}>
			<Upload size={16}/>
			Retry Uploads
		</button>
	{:else}
		<span class="help-text">
			Enable auto-upload in settings to retry failed uploads.
		</span>
	{/if}
{/if}
