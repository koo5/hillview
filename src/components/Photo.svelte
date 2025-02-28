<script>
    import { onMount } from 'svelte';

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
            if (photo.sizes[sizes[i]].width >= containerWidth) {
                selectedUrl = photo.sizes[sizes[i]];
                return;
            }
        }

        selectedUrl = photo.sizes.full;
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
