<svelte:head>
	<title>Timestamp QR Code - Hillview</title>
</svelte:head>

<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { TAURI, autoExportEnabled, autoExportChecked, fetchAutoExportState } from '$lib/tauri';
	import QrTimestamp from "$lib/components/QrTimestamp.svelte";

	onMount(() => {
		fetchAutoExportState();
	});

	function close() {
		goto('/settings/advanced');
	}
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="qr-fullscreen" on:click={close} data-testid="qr-timestamp-page">
	{#if TAURI && $autoExportChecked && !$autoExportEnabled}
		<div class="tracking-warning" data-testid="qr-tracking-warning">
			<strong>Automatic tracking export is disabled!</strong>
			<p>Enable "Automatically export on app start/exit" in Advanced Settings to ensure location/orientation data is saved alongside your QR-timestamped photos.</p>
		</div>
	{/if}
	<QrTimestamp />
</div>

<style>
	.tracking-warning {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		z-index: 10;
		background: rgba(220, 38, 38, 0.92);
		color: white;
		padding: 1.5rem 2rem;
		border-radius: 0.75rem;
		text-align: center;
		max-width: 80%;
		pointer-events: none;
	}

	.tracking-warning strong {
		font-size: 1.25rem;
		display: block;
		margin-bottom: 0.5rem;
	}

	.tracking-warning p {
		font-size: 0.875rem;
		margin: 0;
		line-height: 1.4;
	}

	.qr-fullscreen {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 9999;
		background: white;
		cursor: pointer;
		padding-top: var(--safe-area-inset-top, env(safe-area-inset-top, 0px));
		padding-bottom: var(--safe-area-inset-bottom, env(safe-area-inset-bottom, 0px));
		padding-left: var(--safe-area-inset-left, env(safe-area-inset-left, 0px));
		padding-right: var(--safe-area-inset-right, env(safe-area-inset-right, 0px));
	}
</style>
