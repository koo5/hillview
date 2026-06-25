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
	<button class="close-btn" on:click={onClose} aria-label="Close 360° viewer">&times;</button>
	<div bind:this={container} class="pano-container"></div>
</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 40000;
		background: #000;
	}

	.pano-container {
		width: 100%;
		height: 100%;
	}

	.close-btn {
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

	.close-btn:hover {
		background: rgba(255, 255, 255, 0.3);
	}
</style>
