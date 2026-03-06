<script lang="ts">
	import {onMount, onDestroy} from 'svelte';
	import {browser} from '$app/environment';
	import {photoStats, fetchPhotoStats, hasUploadsToRetry, formatStorageInfo, getPlatformName} from '$lib/photoStatsAdapter';
	import {app} from "$lib/data.svelte";
	import {Upload, Clock, AlertCircle, CheckCircle, Loader, Trash2, Info, HelpCircle} from 'lucide-svelte';
	import RetryUploadsButton from "$lib/components/RetryUploadsButton.svelte";
	import {BROWSER} from '$lib/tauri';
	import {isBackgroundSyncSupported} from '$lib/browser/photoStorage';

	export let addLogEntry: (message: string, type?: 'success' | 'warning' | 'error' | 'info', metadata?: any) => void = () => {};
	export let onRefresh: (() => void | Promise<void>) | null = null;
	export let showDetailedStats = false;

	let showSyncInfo = false;

	const REFRESH_INTERVAL = 5000; // 5 seconds
	let refreshTimer: ReturnType<typeof setInterval> | null = null;

	function isAtTop(): boolean {
		if (!browser) return false;
		return window.scrollY < 50;
	}

	function hasActiveUploads(): boolean {
		const stats = $photoStats;
		if (!stats) return false;
		return stats.pending > 0 || stats.uploading > 0 || stats.processing > 0;
	}

	async function doRefresh() {
		if (!isAtTop()) return;
		if (!hasActiveUploads()) {
			stopTimer();
			return;
		}
		try {
			await fetchPhotoStats();
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
			await fetchPhotoStats();
		} catch (err) {
			console.error('Error fetching photo stats:', err);
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
	$: if ($photoStats) {
		if (hasActiveUploads()) {
			startTimer();
		} else {
			stopTimer();
		}
	}
</script>
{#if $photoStats}
	{#if $app.debug_enabled}
		[debug] Photo Stats: {JSON.stringify($photoStats, null, 2)}
	{/if}
	{#if hasUploadsToRetry($photoStats)}
		<div class="upload-status-bar">
			{#if $photoStats}
					<span class="status-text">
						{$photoStats.pending + $photoStats.failed} pending, {$photoStats.processing} processing
					</span>
			{/if}
			<RetryUploadsButton global={true} {addLogEntry}/>
			<div class="info-text">
				Uploads may be delayed to save battery.
			</div>
		</div>
	{/if}

	{#if BROWSER && $photoStats.storageUsed}
		<div class="storage-info">
			{formatStorageInfo($photoStats)}
		</div>
	{/if}

	{#if BROWSER && !isBackgroundSyncSupported() && ($photoStats.pending > 0 || $photoStats.failed > 0)}
		<div class="sync-limitation-info">
			<Info size={14}/>
			<span>Photos upload only while app is open (background sync not supported)</span>
			<button class="info-button" on:click={() => showSyncInfo = !showSyncInfo} title="Learn more">
				<HelpCircle size={14}/>
			</button>
		</div>
		{#if showSyncInfo}
			<div class="sync-info-details">
				<h4>Background Sync Support</h4>
				<p>Background sync allows photos to upload even when the app is closed or offline.</p>

				<div class="browser-support">
					<div class="support-section">
						<strong>✅ Full Support:</strong>
						<ul>
							<li>Chrome / Edge (Desktop & Android)</li>
							<li>Opera</li>
							<li>Samsung Internet</li>
						</ul>
					</div>

					<div class="support-section">
						<strong>❌ Limited Support:</strong>
						<ul>
							<li>Safari (iOS & macOS) - uploads only while app is open</li>
							<li>Firefox - uploads only while app is open</li>
						</ul>
					</div>
				</div>

				<p class="info-note">
					For best experience on mobile, use Chrome or Edge browser.
				</p>
			</div>
		{/if}
	{/if}

	{#if showDetailedStats}
		<div class="upload-stats" data-testid="upload-stats">
			<div class="stat-item">
				<CheckCircle size={14}/>
				<span>{$photoStats.completed} uploaded</span>
			</div>
			{#if $photoStats.pending > 0}
				<div class="stat-item pending">
					<Clock size={14}/>
					<span>{$photoStats.pending} pending</span>
				</div>
			{/if}
			{#if $photoStats.uploading > 0}
				<div class="stat-item uploading">
					<Upload size={14}/>
					<span>{$photoStats.uploading} uploading</span>
				</div>
			{/if}
			{#if $photoStats.processing > 0}
				<div class="stat-item processing">
					<Loader size={14}/>
					<span>{$photoStats.processing} processing</span>
				</div>
			{/if}
			{#if $photoStats.failed > 0}
				<div class="stat-item failed">
					<Clock size={14}/>
					<span>{$photoStats.failed} waiting to retry</span>
				</div>
			{/if}
			{#if $photoStats.deleted > 0}
				<div class="stat-item deleted">
					<Trash2 size={14}/>
					<span>{$photoStats.deleted} deleted</span>
				</div>
			{/if}
			<!--{#if $devicePhotoStats.failed > 0}-->
			<!--	<div class="stat-item failed">-->
			<!--		<AlertCircle size={14}/>-->
			<!--		<span>{$devicePhotoStats.failed} failed</span>-->
			<!--	</div>-->
			<!--{/if}-->
		</div>
	{/if}
{/if}

<style>
	.info-text {
		text-align: center;
		padding: 10px;
		font-size: 14px;
	}

	.storage-info {
		text-align: center;
		padding: 8px;
		font-size: 0.875rem;
		background: #e0f2fe;
		border: 1px solid #7dd3fc;
		border-radius: 6px;
		margin-bottom: 12px;
		color: #0369a1;
	}

	.sync-limitation-info {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		padding: 8px;
		font-size: 0.875rem;
		background: #fff7ed;
		border: 1px solid #fb923c;
		border-radius: 6px;
		margin-bottom: 12px;
		color: #c2410c;
		position: relative;
	}

	.info-button {
		background: none;
		border: none;
		cursor: pointer;
		padding: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #c2410c;
		transition: opacity 0.2s;
	}

	.info-button:hover {
		opacity: 0.7;
	}

	.sync-info-details {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		padding: 16px;
		margin-bottom: 16px;
		font-size: 0.875rem;
	}

	.sync-info-details h4 {
		margin: 0 0 12px 0;
		color: #1f2937;
		font-size: 1rem;
	}

	.sync-info-details p {
		margin: 8px 0;
		color: #4b5563;
		line-height: 1.5;
	}

	.browser-support {
		margin: 16px 0;
		display: flex;
		gap: 24px;
		flex-wrap: wrap;
	}

	.support-section {
		flex: 1;
		min-width: 200px;
	}

	.support-section strong {
		display: block;
		margin-bottom: 8px;
		color: #1f2937;
	}

	.support-section ul {
		margin: 0;
		padding-left: 20px;
		color: #6b7280;
	}

	.support-section li {
		margin: 4px 0;
	}

	.info-note {
		margin-top: 12px;
		padding: 8px 12px;
		background: #f0f9ff;
		border-left: 3px solid #0284c7;
		color: #0c4a6e;
		font-size: 0.825rem;
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

	.stat-item.processing {
		color: #8b5cf6;
	}

	.stat-item.failed {
		color: #ef4444;
	}

	.stat-item.deleted {
		color: #6b7280;
	}
</style>
