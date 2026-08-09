<script lang="ts">
import { onMount } from 'svelte';
import { zoomViewData, pendingZoomView, pendingZoomViewError, type ZoomViewInitialBounds } from '$lib/zoomView.svelte';
import '@annotorious/openseadragon/annotorious-openseadragon.css';

let OpenSeadragonViewer: any = null;
let Pannellum360Viewer: any = null;
let initialBounds: ZoomViewInitialBounds | null = null;

// Capture initial bounds from the pending state. This component lives in
// +layout, so the local capture is session-long state — two rules keep it
// honest:
//
// Deliberately NOT guarded by `!initialBounds`: a browser Back closes the
// overlay via +layout's beforeNavigate (pathname change), which never runs
// closeZoomView — so the capture survives, and with the guard a subsequent
// open with NEW bounds (a different annotation link) kept applying the stale
// first value.
$: if ($pendingZoomView) {
	initialBounds = { ...$pendingZoomView };
}
// And drop the capture once the zoomview is fully closed (both stores null —
// e.g. after that nav-close): otherwise the next open WITHOUT pending bounds
// (double-click on the photo overlay) would apply the stale window to an
// unrelated photo. Safe against the open sequence: pending is set before
// data, and stays set while the viewer is open.
$: if (!$pendingZoomView && !$zoomViewData) {
	initialBounds = null;
}

onMount(async () => {
	const [osdModule, panoModule] = await Promise.all([
		import('./OpenSeadragonViewer.svelte'),
		import('./Pannellum360Viewer.svelte'),
	]);
	OpenSeadragonViewer = osdModule.default;
	Pannellum360Viewer = panoModule.default;
});

function closeZoomView() {
	zoomViewData.set(null);
	pendingZoomView.set(null);
	pendingZoomViewError.set(null);
	initialBounds = null;
}

function closePendingView() {
	pendingZoomView.set(null);
	pendingZoomViewError.set(null);
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
		{#if $pendingZoomViewError}
			<!-- The photo will never arrive (deleted / gone) — say so instead of
			     spinning forever; see verifyUrlRequestedPhoto in Map.svelte -->
			<div class="pending-content" data-testid="zoom-view-pending-error">
				<p>{$pendingZoomViewError}</p>
			</div>
		{:else}
			<div class="pending-content">
				<div class="spinner"></div>
				<p>Loading photo...</p>
			</div>
		{/if}
	</div>
{/if}

{#if $zoomViewData && $zoomViewData.equirectangular && Pannellum360Viewer}
	<svelte:component this={Pannellum360Viewer} data={$zoomViewData} onClose={closeZoomView} />
{:else if $zoomViewData && OpenSeadragonViewer}
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
