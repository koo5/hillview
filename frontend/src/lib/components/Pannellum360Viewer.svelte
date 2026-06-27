<script lang="ts">
	/**
	 * Pannellum360Viewer.svelte
	 *
	 * Full-screen equirectangular (360°) panorama viewer powered by Pannellum.
	 * Shown when the user taps a photo whose projection is 'equirectangular'.
	 */

	import { onMount, onDestroy } from 'svelte';
	import type { ZoomViewData } from '$lib/zoomView.svelte';
	import 'pannellum/build/pannellum.css';

	export let data: ZoomViewData;
	export let onClose: () => void;

	let container: HTMLDivElement;
	let viewer: any = null;

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	onMount(async () => {
		// Pannellum attaches to window.pannellum — load dynamically to keep it browser-only
		await import('pannellum/build/pannellum.js');
		const pannellum = (window as any).pannellum;
		if (!pannellum || !container) return;

		viewer = pannellum.viewer(container, {
			type: 'equirectangular',
			panorama: data.url || data.fallback_url,
			autoLoad: true,
			showControls: true,
			crossOrigin: 'anonymous',
			hfov: 100,
		});
	});

	onDestroy(() => {
		try { viewer?.destroy(); } catch (e) { console.error('Error destroying Pannellum viewer:', e); }
		viewer = null;
	});
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="overlay" role="dialog" aria-modal="true" aria-label="360 degree panorama viewer" data-testid="pannellum-360-viewer">
	<button class="close-btn" on:click={onClose} aria-label="Close 360° viewer" data-testid="pannellum-360-close">
		<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
			<path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
		</svg>
	</button>
	<div bind:this={container} class="pano-container"></div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		/* Match OpenSeadragonViewer's overlay so the viewer sits above the app
		   chrome (hamburger menu, per-photo gallery buttons) like the flat
		   zoom view does. A lower value lets those controls bleed through. */
		z-index: 999999;
		background: #000;
	}

	.pano-container {
		width: 100%;
		height: 100%;
	}

	/* Matches OpenSeadragonViewer's close button: a near-opaque white circle with
	   a dark glyph, which stays legible against any sky. */
	.close-btn {
		position: absolute;
		top: calc(12px + var(--safe-area-inset-top, 0px));
		right: calc(12px + var(--safe-area-inset-right, 0px));
		/* Local to the .overlay stacking context — just needs to clear Pannellum's
		   own controls (z-index ~1-4). */
		z-index: 10;
		background: rgba(255, 255, 255, 0.85);
		border: none;
		border-radius: 50%;
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: #333;
	}

	.close-btn:hover { background: rgba(255, 255, 255, 1); }
</style>
