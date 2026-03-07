<script lang="ts">
import { onMount } from 'svelte';
import { zoomViewData } from '$lib/zoomView.svelte';
import '@annotorious/openseadragon/annotorious-openseadragon.css';

let OpenSeadragonViewer: any = null;

onMount(async () => {
	const module = await import('./OpenSeadragonViewer.svelte');
	OpenSeadragonViewer = module.default;
});

function closeZoomView() {
	zoomViewData.set(null);
}
</script>

{#if $zoomViewData && OpenSeadragonViewer}
	<svelte:component this={OpenSeadragonViewer} data={$zoomViewData} onClose={closeZoomView} />
{/if}
