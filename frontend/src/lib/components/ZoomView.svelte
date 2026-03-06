<script lang="ts">
import { zoomViewData } from '$lib/zoomView.svelte';
import OpenSeadragonViewer from './OpenSeadragonViewer.svelte';
import '@annotorious/openseadragon/annotorious-openseadragon.css';

function closeZoomView() {
zoomViewData.set(null);
}
</script>

{#if $zoomViewData}
<OpenSeadragonViewer data={$zoomViewData} onClose={closeZoomView} />
{/if}
