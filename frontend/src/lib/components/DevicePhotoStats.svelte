<script lang="ts">
	import {onMount, onDestroy} from 'svelte';
	import {browser} from '$app/environment';
	import {devicePhotoStats, fetchDevicePhotoStats, hasUploadsToRetry} from '$lib/devicePhotoStats';
	import {app} from "$lib/data.svelte";
	import {Upload, Clock, AlertCircle, CheckCircle} from 'lucide-svelte';
	import RetryUploadsButton from "$lib/components/RetryUploadsButton.svelte";

	export let addLogEntry: (message: string, type?: 'success' | 'warning' | 'error' | 'info', metadata?: any) => void = () => {};
	export let onRefresh: (() => void | Promise<void>) | null = null;

	const REFRESH_INTERVAL = 5000; // 5 seconds
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	function isAtTop(): boolean {
		if (!browser) return false;
		return window.scrollY < 50;
	}

	function hasActiveUploads(): boolean {
		const stats = $devicePhotoStats;
		if (!stats) return false;
		return stats.pending > 0 || stats.uploading > 0;
	}

	async function doRefresh() {
		if (!isAtTop()) return;
		if (!hasActiveUploads()) {
			stopTimer();
			return;
		}
		try {
			await fetchDevicePhotoStats();
			await onRefresh?.();
		} catch (err) {
			// Silently handle errors during auto-refresh to prevent unhandled promise rejections
			console.error('Error during auto-refresh:', err);
		}
	}

	function startTimer() {
		if (refreshTimer) return;
		refreshTimer = setInterval(doRefresh, REFRESH_INTERVAL);
	}

	function stopTimer() {
		if (refreshTimer) {
			clearInterval(refreshTimer);
			refreshTimer = null;
		}
	}

	onMount(async () => {
		try {
			await fetchDevicePhotoStats();
		} catch (err) {
			console.error('Error fetching device photo stats:', err);
		}
		// Start timer if there are active uploads
		if (hasActiveUploads()) {
			startTimer();
		}
	});

	onDestroy(() => {
		stopTimer();
	});

	// Reactively start/stop timer based on upload status
	$: if ($devicePhotoStats) {
		if (hasActiveUploads()) {
			startTimer();
		} else {
			stopTimer();
		}
	}
</script>
{#if $devicePhotoStats}
	{#if $app.debug_enabled}
		[debug] Photo Stats: {JSON.stringify($devicePhotoStats, null, 2)}
	{/if}
	{#if hasUploadsToRetry($devicePhotoStats)}
		<div class="upload-status-bar">
			{#if $devicePhotoStats}
					<span class="status-text">
						{$devicePhotoStats.pending + $devicePhotoStats.failed} photos waiting to upload
					</span>
			{/if}
			<RetryUploadsButton global={true} {addLogEntry}/>
			<div class="info-text">
				Uploads may be delayed to save battery.
			</div>
		</div>
	{/if}
	<div class="upload-stats" data-testid="upload-stats">
		<div class="stat-item">
			<CheckCircle size={14}/>
			<span>{$devicePhotoStats.completed} uploaded</span>
		</div>
		{#if $devicePhotoStats.pending > 0}
			<div class="stat-item pending">
				<Clock size={14}/>
				<span>{$devicePhotoStats.pending} pending</span>
			</div>
		{/if}
		{#if $devicePhotoStats.uploading > 0}
			<div class="stat-item uploading">
				<Upload size={14}/>
				<span>{$devicePhotoStats.uploading} uploading</span>
			</div>
		{/if}
		{#if $devicePhotoStats.failed > 0}
			<div class="stat-item failed">
				<AlertCircle size={14}/>
				<span>{$devicePhotoStats.failed} failed</span>
			</div>
		{/if}
	</div>
{/if}

<style>
	.info-text {
		text-align: center;
		padding: 10px;
		font-size: 14px;
	}

	.upload-status-bar {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 12px;
		padding: 0px 0px;
		background: #fef3c7;
		border: 1px solid #fcd34d;
		border-radius: 8px;
		margin-bottom: 16px;
	}

	.status-text {
		font-size: 0.8rem;
		color: #92400e;
	}

	.upload-stats {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
		padding: 2px 0px;
		background: #f8fafc;

		border-radius: 8px;
		margin: 0px;
	}

	.stat-item {
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 0.875rem;
		color: #10b981;
	}

	.stat-item.pending {
		color: #403520;
	}

	.stat-item.uploading {
		color: #3b82f6;
	}

	.stat-item.failed {
		color: #ef4444;
	}
</style>
