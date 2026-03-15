<svelte:head>
	<title>Timestamp QR Code - Hillview</title>
</svelte:head>

<script lang="ts">
	import { goto } from '$app/navigation';
	import QrTimestamp from "$lib/components/QrTimestamp.svelte";

	function close() {
		goto('/settings/advanced');
	}
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="qr-fullscreen" on:click={close} data-testid="qr-timestamp-page">
	<QrTimestamp />
</div>

<style>
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
