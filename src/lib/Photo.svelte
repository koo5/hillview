<script>
    import { onMount } from 'svelte';

    export let photo = null;
    export let className = '';
    export let fetchPriority = 'auto';
    
    let containerWidth = 0;
    let containerElement;
    let selectedUrl;
    
    onMount(() => {
        updateSelectedUrl();
        
        // Set up resize observer to update the selected URL when container size changes
        const resizeObserver = new ResizeObserver(() => {
            updateSelectedUrl();
        });
        
        if (containerElement) {
            resizeObserver.observe(containerElement);
        }
        
        return () => {
            if (containerElement) {
                resizeObserver.disconnect();
            }
        };
    });
    
    function updateSelectedUrl() {
        if (!photo) {
            selectedUrl = '';
            return;
        }
        
        if (!photo.scaled || !containerElement) {
            selectedUrl = photo.url;
            return;
        }
        
        containerWidth = containerElement.clientWidth;
        
        // Find the best scaled version based on container width
        const availableWidths = Object.keys(photo.scaled)
            .map(width => parseInt(width, 10))
            .sort((a, b) => a - b);
        
        // Find the smallest width that is larger than the container
        const bestWidth = availableWidths.find(width => width >= containerWidth) || 
                          availableWidths[availableWidths.length - 1];
        
        selectedUrl = bestWidth ? photo.scaled[bestWidth] : photo.url;
    }
</script>

<div bind:this={containerElement} class="photo-wrapper {className}">
    {#if photo}
        <img 
            src={selectedUrl} 
            alt={photo.file} 
            class="photo" 
            fetchpriority={fetchPriority} 
        />
    {/if}
</div>

<style>
    .photo-wrapper {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        width: 100%;
    }
    
    .photo {
        display: block;
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }
</style>
