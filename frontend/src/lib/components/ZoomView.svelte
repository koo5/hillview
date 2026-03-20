<script lang="ts">
import { onMount } from 'svelte';
import { zoomViewData, pendingZoomView, type ZoomViewInitialBounds } from '$lib/zoomView.svelte';
import '@annotorious/openseadragon/annotorious-openseadragon.css';

let OpenSeadragonViewer: any = null;
let initialBounds: ZoomViewInitialBounds | null = null;

// Capture initial bounds from pending state when it first appears
$: if ($pendingZoomView && !initialBounds) {
	initialBounds = { ...$pendingZoomView };
}

onMount(async () => {
	const module = await import('./OpenSeadragonViewer.svelte');
	OpenSeadragonViewer = module.default;
});

function closeZoomView() {
	zoomViewData.set(null);
	pendingZoomView.set(null);
	initialBounds = null;
}

function closePendingView() {
	pendingZoomView.set(null);
	initialBounds = null;
}

function handlePendingKeydown(e: KeyboardEvent) {
	if (e.key === 'Escape') closePendingView();
}
</script>

{#if $pendingZoomView && !$zoomViewData}
	<!-- Pending state: waiting for photo data to load -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="pending-overlay" data-testid="zoom-view-pending" on:keydown={handlePendingKeydown}>
		<button class="pending-close-btn" on:click={closePendingView} data-testid="zoom-view-pending-close" aria-label="Close">
			&times;
		</button>
		<div class="pending-content">
			<div class="spinner"></div>
			<p>Loading photo...</p>
		</div>
	</div>
{/if}

{#if $zoomViewData && OpenSeadragonViewer}
	<svelte:component this={OpenSeadragonViewer} data={$zoomViewData} onClose={closeZoomView} {initialBounds} />
{/if}

<style>
	.pending-overlay {
		position: fixed;
		inset: 0;
		z-index: 40000;
		background: rgba(0, 0, 0, 0.85);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.pending-close-btn {
		position: absolute;
		top: calc(16px + var(--safe-area-inset-top, 0px));
		right: calc(16px + var(--safe-area-inset-right, 0px));
		z-index: 40001;
		background: rgba(255, 255, 255, 0.15);
		border: none;
		color: white;
		font-size: 28px;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		line-height: 1;
	}

	.pending-close-btn:hover {
		background: rgba(255, 255, 255, 0.3);
	}

	.pending-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
		color: rgba(255, 255, 255, 0.8);
		font-size: 14px;
	}

	.spinner {
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background:
			radial-gradient(farthest-side, rgba(255, 255, 255, 0.8), 94%, transparent) top/6px 6px no-repeat,
			conic-gradient(transparent 30%, rgba(255, 255, 255, 0.8));
		mask: radial-gradient(farthest-side, transparent calc(100% - 6px), black 0);
		-webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 6px), black 0);
		animation: spin 1s infinite linear;
	}

	@keyframes spin {
		100% { transform: rotate(1turn); }
	}
</style>
