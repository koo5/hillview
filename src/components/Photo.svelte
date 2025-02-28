<script>
    import { onMount } from 'svelte';
    import { app } from '$lib/data.svelte.js';

    export let photo = null;
    export let className = '';
    let fetchPriority = className === 'front' ? 'high' : 'auto';
    
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

    $: updateSelectedUrl(photo);
    
    function updateSelectedUrl() {

        if (!containerElement) {
            return;
        }

        if (!photo) {
            selectedUrl = '';
            return;
        }
        
        if (!photo.sizes) {
            selectedUrl = photo.url;
            return;
        }
        
        containerWidth = containerElement.clientWidth;
        
        // Find the best scaled version based on container width. Take the 'full' size if this fails
        const sizes = Object.keys(photo.sizes).filter(size => size !== 'full').sort((a, b) => a - b);
        for (let i = 0; i < sizes.length; i++) {
            const size = sizes[i];
            //console.log('size:', size);
            if (size >= containerWidth) {
                selectedUrl = photo.sizes[sizes[i]];
                return;
            }
        }

        selectedUrl = photo.sizes.full;
    }
</script>

{#if $app.debug === 2}
<div class="debug">
    <b>Debug Information</b><br>
    <b>Container width:</b> {containerWidth}<br>
    <b>Selected URL:</b> {selectedUrl}
</div>
{/if}

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
    .debug {
        overflow: auto;
        position: absolute;
        top: 0;
        left: 0;
        padding: 0.5rem;
        background: white;
        border: 1px solid black;
        z-index: 31000;
        width: 300px; /* Fixed width */
        height: 400px; /* Fixed height */
    }
    .photo-wrapper {
        display: flex;
        justify-content: center;
    }
    
    .photo {
        border: 1px solid black;
        display: block;
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }

    /* Front image is centered and on top */
    .front {
        width: 100%;
        position: relative;
        z-index: 2;
    }

    /* Side images are absolutely positioned and vertically centered */
    .left {
        opacity: 0.4;
        position: absolute;
        top: 50%;
        transform: translateY(-80%);
        z-index: 1;
        /* Optionally, set a width to control how much of the side image shows */
        width: 90%;
        left: 0;
        mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
    }

    .right {
        opacity: 0.4;
        position: absolute;
        top: 50%;
        transform: translateY(-20%);
        z-index: 1;
        /* Optionally, set a width to control how much of the side image shows */
        width: 90%;
        right: 0;
        mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
    }

</style>
