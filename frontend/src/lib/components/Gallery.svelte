<script lang="ts">
    import {photoInFront, photosInRange, updateBearing} from "$lib/mapState";
    import Photo from "./Photo.svelte";
    import Spinner from "./Spinner.svelte";
    import {anySourceLoading} from "$lib/data.svelte.js";
    import type {PhotoData} from '$lib/sources';

    let clientWidth: number;

    function handleThumbnailClick(photo: PhotoData) {
        updateBearing(photo.bearing);
    }

    // Log photo count changes
    /*
    $: if ($photosInRange) {
        console.log(`🢄Gallery: Displaying ${$photosInRange.length} photos in range`);
    }*/
</script>

<div class="gallery-wrapper">
    <!--{#if $app.displayMode !== 'max'}-->
    <!--    <div class="thumbnails-top">-->
    <!--        {#each $photosInRange as photo}-->
    <!--            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>-->
    <!--                {#if photo.isDevicePhoto}-->
    <!--                    <img src={getDevicePhotoUrl(photo.url)} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>-->
    <!--                {:else if photo.sizes && photo.sizes[50]}-->
    <!--                    <img src={photo.sizes[50].url} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>-->
    <!--                {/if}-->
    <!--            </div>-->
    <!--        {/each}-->
    <!--    </div>-->
    <!--{/if}-->

    <div bind:clientWidth class="photo-container">
        <!--{#if $photo_to_left}-->
        <!--    <Photo photo={$photo_to_left} className="left" />-->
        <!--{/if}-->
        {#if $photoInFront}
            <Photo photo={$photoInFront} className="front" {clientWidth}/>
        {:else}
            <div class="no-photo">
                {#if $anySourceLoading}
                    <div class="loading-container">
                        <Spinner show={true} color="#ffffff" />
                        <p>Loading photos...</p>
                    </div>
                {:else}
                    <p>No photos in range</p>
                {/if}
            </div>
        {/if}
        <!--{#if $photo_to_right}-->
        <!--    <Photo photo={$photo_to_right} className="right" />-->
        <!--{/if}-->
    </div>

    <!--{#if $app.displayMode !== 'max'}-->
    <!--    <div class="thumbnails-bottom">-->
    <!--        {#each $photosInRange as photo}-->
    <!--            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>-->
    <!--                {#if photo.isDevicePhoto}-->
    <!--                    <img src={getDevicePhotoUrl(photo.url)} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>-->
    <!--                {:else if photo.sizes && photo.sizes[50]}-->
    <!--                    <img src={photo.sizes[50].url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>-->
    <!--                {/if}-->
    <!--            </div>-->
    <!--        {/each}-->
    <!--    </div>-->
    <!--{/if}-->


</div>


<style>
    .gallery-wrapper {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        max-height: 100%;
        /*background: linear-gradient(135deg, #388E3C, #689F38);*/
		background: linear-gradient(135deg, #000000, #388E3C);
    }

    /*.thumbnails-top, .thumbnails-bottom {*/
    /*    display: flex;*/
    /*    overflow-x: auto;*/
    /*    padding: 1px;*/
    /*    background-color: rgba(0, 0, 0, 0.5);*/
    /*    height: 50px;*/
    /*    z-index: 30000;*/
    /*}*/

    /*.thumbnails-bottom {*/
    /*    flex-direction: row-reverse;*/
    /*}*/

    /*.thumbnail {*/
    /*    flex: 0 0 auto;*/
    /*    margin: 0 5px;*/
    /*    cursor: pointer;*/
    /*    transition: transform 0.2s;*/
    /*}*/

    /*.thumbnail:hover {*/
    /*    transform: scale(1.1);*/
    /*}*/

    /*.thumbnail img {*/
    /*    height: 50px;*/
    /*    width: 50px;*/
    /*    object-fit: cover;*/
    /*    border: 2px solid;*/
    /*    border-radius: 4px;*/
    /*}*/

    /*ul {*/
    /*    margin: 0.3em;*/
    /*}*/

    /*.no-photo {*/
    /*    */
    /*}*/

    .photo-container {
        position: relative;
        flex: 1;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    .no-photo {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 100%;
        color: #ffffff;
    }

    .loading-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }

    .loading-container p {
        margin: 0;
        font-size: 1rem;
        opacity: 0.8;
    }


</style>
