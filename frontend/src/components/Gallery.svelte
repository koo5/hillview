<script lang="ts">
    import {
        app,
        turn_to_photo_to, 
        reversed
    } from "$lib/data.svelte";
    import {
        spatialState,
        visualState,
        photosInArea,
        photoInFront,
        photoToLeft,
        photoToRight,
        updateBearing
    } from "$lib/mapState";
    import {dms} from "$lib/utils";
    import Photo from "./Photo.svelte";
    import { getDevicePhotoUrl } from '$lib/devicePhotoHelper';
    import type { PhotoData } from '$lib/sources';

    let clientWidth: number;
    
    function handleThumbnailClick(photo: PhotoData) {
        updateBearing(photo.bearing);
    }
</script>

<div class="gallery-wrapper">
    {#if $app.displayMode !== 'max'}
        <div class="thumbnails-top">
            {#each [] as photo}
                <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>
                    {#if photo.isDevicePhoto}
                        {#await getDevicePhotoUrl(photo.url) then url}
                            <img src={url} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>
                        {/await}
                    {:else if photo.sizes && photo.sizes[50]}
                        <img src={photo.sizes[50].url} alt="Thumbnail" style:border-color={photo.bearing_color || '#ccc'}/>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}

    <div class="photo-container" bind:clientWidth >
        <!--{#if $photo_to_left}-->
        <!--    <Photo photo={$photo_to_left} className="left" />-->
        <!--{/if}-->
        {#if $photoInFront}
            <Photo photo={$photoInFront} className="front" {clientWidth} />
        {/if}
        <!--{#if $photo_to_right}-->
        <!--    <Photo photo={$photo_to_right} className="right" />-->
        <!--{/if}-->
    </div>

    {#if $app.displayMode !== 'max'}
        <div class="thumbnails-bottom">
            {#each [] as photo}
                <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>
                    {#if photo.isDevicePhoto}
                        {#await getDevicePhotoUrl(photo.url) then url}
                            <img src={url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>
                        {/await}
                    {:else if photo.sizes && photo.sizes[50]}
                        <img src={photo.sizes[50].url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>
                    {/if}
                </div>
            {/each}
        </div>
    {/if}

    {#if $app.debug === 1}
        <div class="debug">
            <b>Debug Information</b><br>
            <b>Bearing:</b>  {$visualState.bearing}<br>
            <b>Pos.center:</b> {$spatialState.center}<br>
            <b>Left:</b>  {$photoToLeft?.file}<br>
            <b>Front:</b> {$photoInFront?.file}<br>
            <b>Right:</b>  {$photoToRight?.file}<br>
            <b>Photos in area:</b> {$photosInArea.length}<br>
            <b>Range:</b> {$spatialState.range / 1000} km<br>
            <b>Photos to left:</b>
            {JSON.stringify([], null, 2)}
<!--            <ul>-->
<!--            {#each [] as photo}-->
<!--                <li>{photo.id},{photo.file}-->
<!--                    {JSON.stringify(photo.sizes, null, 2)}-->
<!--                </li>-->
<!--            {/each}-->
<!--            </ul>-->
            <b>Photos to right:</b>
            <ul>
            {#each [] as photo}
                <li>{photo.id},{photo.file}
                    {JSON.stringify(photo.sizes, null, 2)}
                </li>
            {/each}
            </ul>

<!--            <details>-->
<!--                <summary><b>photos_to_left:</b></summary>-->
<!--                <pre>{JSON.stringify($photos_to_left, null, 2)}</pre>-->
<!--                >-->
<!--            </details>-->
<!--            <details>-->
<!--                <summary><b>photos_to_right:</b></summary>-->
<!--                <pre>{JSON.stringify($photos_to_right, null, 2)}</pre>-->
<!--            </details>-->
        </div>
    {/if}

</div>


<style>
    .gallery-wrapper {
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        max-height: 100%;
    }

    .thumbnails-top, .thumbnails-bottom {
        display: flex;
        overflow-x: auto;
        padding: 1px;
        background-color: rgba(0, 0, 0, 0.5);
        height: 50px;
        z-index: 30000;
    }

    .thumbnails-bottom {
        flex-direction: row-reverse;
    }

    .thumbnail {
        flex: 0 0 auto;
        margin: 0 5px;
        cursor: pointer;
        transition: transform 0.2s;
    }

    .thumbnail:hover {
        transform: scale(1.1);
    }

    .thumbnail img {
        height: 50px;
        width: 50px;
        object-fit: cover;
        border: 2px solid;
        border-radius: 4px;
    }

    .debug {
        overflow: auto;
        position: absolute;
        top: 0;
        left: 0;
        padding: 0.5rem;
        background: white;
        border: 1px solid black;
        z-index: 31000;
        width: 90%;
        height: 90%;
    }

    .photo-container {
        position: relative;
        flex: 1;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    ul {
        margin: 0.3em;
    }
</style>
