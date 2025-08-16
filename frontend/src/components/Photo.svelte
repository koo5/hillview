<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { app } from '$lib/data.svelte';
    import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
    import type { PhotoData } from '$lib/sources';

    export let photo: PhotoData | null = null;
    export let className = '';
    export let clientWidth: number | undefined = undefined;

    let clientWidth2: number | undefined;

    let fetchPriority = className === 'front' ? 'high' : 'auto';
    
    let containerElement: HTMLElement | undefined;
    let selectedUrl: string | undefined;
    let selectedSize: any;
    let width = 100;
    let height = 100;
    let devicePhotoUrl: string | null = null;
    let bg_style_stretched_photo;
    let border_style;

    // enable for stretched backdrop
    //$: bg_style_stretched_photo = photo.sizes?.[50] ? `background-image: url(${photo.sizes[50].url});` : ''

    $: border_style = className === 'front' && photo ? 'border: 4px dotted #4a90e2;' : '';
    console.log('border_style:', border_style);

    $: if (photo || clientWidth || containerElement) updateSelectedUrl();
    
    async function updateSelectedUrl() {

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
            devicePhotoUrl = null;
            return;
        }
        
        // Handle device photos specially
        if (photo.isDevicePhoto && photo.url) {
            try {
                devicePhotoUrl = await getDevicePhotoUrl(photo.url);
                selectedUrl = devicePhotoUrl;
                return;
            } catch (error) {
                console.error('Failed to load device photo:', error);
                selectedUrl = '';
                return;
            }
        }
        
        if (!photo.sizes) {
            selectedUrl = photo.url;
            return;
        }

        // Find the best scaled version based on container width. Take the 'full' size if this fails
        const sizes = Object.keys(photo.sizes).filter(size => size !== 'full').sort((a, b) => Number(a) - Number(b));
        let p: any;
        for (let i = 0; i < sizes.length; i++) {
            const size = sizes[i];
            //console.log('size:', size);
            if (Number(size) >= clientWidth2) {
                p = photo.sizes[sizes[i]];
                selectedSize = size;
                width = p.width;
                height = p.height;
                
                // Handle device photo URLs
                if (photo.isDevicePhoto) {
                    selectedUrl = await getDevicePhotoUrl(p.url);
                } else {
                    selectedUrl = p.url;
                }
                return;
            }
        }
        selectedSize = 'full';
        width = photo.sizes.full?.width || p?.width || 0;
        height = photo.sizes.full?.height || p?.height || 0;
        
        // Handle device photo URLs for full size
        if (photo.isDevicePhoto && photo.sizes.full) {
            selectedUrl = await getDevicePhotoUrl(photo.sizes.full.url);
        } else {
            selectedUrl = photo.sizes.full?.url || '';
        }
    }



</script>
{#if $app.debug === 5}
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
            style="{bg_style_stretched_photo} {border_style}"
            fetchpriority={fetchPriority as any}
            data-testid="main-photo"
            data-photo={JSON.stringify(photo)}
        />
        {/key}
    {/if}
</div>

<style>
    .debug {
        overflow: auto;
        position: absolute;
        top: 130;
        left: 100;
        padding: 0.5rem;
        background: #f0f070;
        border: 1px solid black;
        z-index: 1000;
        width: 320px; /* Fixed width */
        height: 320px; /* Fixed height */
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
