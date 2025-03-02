<script>
    import { onMount } from 'svelte';
    import { app } from '$lib/data.svelte.js';

    export let photo = null;
    export let className = '';
    export let clientWidth;

    let clientWidth2;

    let fetchPriority = className === 'front' ? 'high' : 'auto';
    
    let containerElement;
    let selectedUrl;
    let selectedSize;
    let width = 100;
    let height = 100;

    let border_style;
    $: border_style = className === 'front' ? 'border: 4px dotted '+ photo?.bearing_color +';' : '';

    $: updateSelectedUrl(photo, clientWidth, containerElement);
    
    function updateSelectedUrl() {

        if (clientWidth)
            clientWidth2 = clientWidth;
        else
            if (!clientWidth2)
                clientWidth2 = 500;

        //console.log('updateSelectedUrl clientWidth:', clientWidth2);

        if (!containerElement) {
            return;
        }

        if (!photo) {
            selectedUrl = '';
            return;
        }
        
        if (!photo.sizes) {
//            selectedUrl = photo.url;
            return;
        }

        // Find the best scaled version based on container width. Take the 'full' size if this fails
        const sizes = Object.keys(photo.sizes).filter(size => size !== 'full').sort((a, b) => a - b);
        for (let i = 0; i < sizes.length; i++) {
            const size = sizes[i];
            //console.log('size:', size);
            if (size >= clientWidth2) {
                let p = photo.sizes[sizes[i]];
                selectedSize = size;
                width = p.width;
                height = p.height;
                selectedUrl = p.url;
                return;
            }
        }
        selectedSize = 'full';
        width = photo.sizes.full.width;
        height = photo.sizes.full.height;
        selectedUrl = photo.sizes.full.url;
    }
</script>

{#if $app.debug === 2}
<div class="debug">
    <b>Debug Information</b><br>
    <b>clientWidth2:</b> {clientWidth2}<br>
    <b>Selected URL:</b> {selectedUrl}
    <b>Selected Size:</b> {selectedSize}
    <b>Width:</b> {width}
    <b>Height:</b> {height}

</div>
{/if}

<div bind:this={containerElement} class="photo-wrapper" >
    {#if photo}
        {#key selectedUrl}
        <img
            src={selectedUrl}
            alt={photo.file}
            class="{className} photo"
            style="background-image: url({photo.sizes[50].url}); {border_style}"
            fetchpriority={fetchPriority}
        />
        {/key}
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
        /*width: 100%;*/
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        background-repeat: no-repeat;

    }

    .photo {
        object-fit: contain;
        background-size: cover;
        -o-background-size: cover;
    }
    

    /* Front image is centered and on top */
    .front {
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
