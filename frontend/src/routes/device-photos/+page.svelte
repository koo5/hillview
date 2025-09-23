<script lang="ts">
	import {onMount} from 'svelte';
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import {TAURI} from '$lib/tauri';
	import {invoke} from "@tauri-apps/api/core";

	let device: any = null;
	let isLoading = true;
	let error: string | null = null;

	onMount(() => {
		setTimeout(() => {
			fetchDevicePhotos();
		}, 100);
	});

	async function fetchDevicePhotos() {
		if (!TAURI) {
			error = "Device photos are only available in the Android app";
			isLoading = false;
			return;
		}

		try {
			isLoading = true;
			device = await invoke('plugin:hillview|get_device_photos') as {lastUpdated: any, photos: any[]};
			console.log('Device photos response:', JSON.stringify(device));
		} catch (err) {
			console.error('Error fetching device photos:', err);
			error = `Failed to fetch device photos: ${err}`;
		} finally {
			isLoading = false;
		}
	}

	async function refreshDevicePhotos() {
		error = null;
		await fetchDevicePhotos();
	}
</script>

<StandardHeaderWithAlert
	title="Device Photos"
	showMenuButton={true}
	fallbackHref="/photos"
/>

<StandardBody>
	{#if error}
		<div class="error-message" data-testid="error-message">{error}</div>
	{/if}

	<div class="device-photos-section" data-testid="device-photos-section">
		<div class="section-header">
			<h2>Device Photos (for Debugging)</h2>
			<button
				class="refresh-button"
				on:click={refreshDevicePhotos}
				disabled={isLoading}
				data-testid="refresh-button"
			>
				{#if isLoading}
					Refreshing...
				{:else}
					Refresh
				{/if}
			</button>
		</div>

		{#if isLoading}
			<div class="loading-container" data-testid="loading-container">
				<p>Loading device photos...</p>
			</div>
		{:else if device}
			<div class="device-data" data-testid="device-data">
				<pre>{JSON.stringify(device, null, 2)}</pre>
			</div>
		{:else}
			<div class="no-data" data-testid="no-data">
				<p>No device photos data available</p>
			</div>
		{/if}
	</div>
</StandardBody>

<style>
	.device-photos-section {
		background-color: white;
		border-radius: 8px;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
		margin-bottom: 32px;
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 20px;
	}

	.section-header h2 {
		margin: 0;
		color: #444;
	}

	.refresh-button {
		padding: 8px 16px;
		background-color: #4a90e2;
		color: white;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 0.3s;
	}

	.refresh-button:hover:not(:disabled) {
		background-color: #357abd;
	}

	.refresh-button:disabled {
		background-color: #94a3b8;
		cursor: not-allowed;
	}

	.loading-container {
		display: flex;
		justify-content: center;
		padding: 40px 0;
	}

	.device-data {
		background-color: #f8f9fa;
		border: 1px solid #e9ecef;
		border-radius: 4px;
		padding: 16px;
		overflow-x: auto;
	}

	.device-data pre {
		margin: 0;
	}

	.no-data {
		text-align: center;
		color: #666;
		padding: 40px 0;
	}

	.error-message {
		background-color: #ffebee;
		color: #c62828;
		padding: 12px;
		border-radius: 4px;
		margin-bottom: 20px;
	}
</style>
