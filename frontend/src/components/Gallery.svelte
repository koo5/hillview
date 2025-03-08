<script>
    import {
        app,
        pos,
        pos2,
        bearing,
        photos_in_area,
        photos_in_range,
        photos_to_left,
        photos_to_right,
        photo_in_front,
        photo_to_left,
        photo_to_right,
        update_bearing,
        turn_to_photo_to, reversed
    } from "$lib/data.svelte.ts";
    import {dms} from "$lib/utils.ts";
    import Photo from "./Photo.svelte";

    let clientWidth;
    
    function handleThumbnailClick(photo) {
        bearing.set(photo.bearing);
    }
</script>

<div class="gallery-wrapper">
    <div class="thumbnails-top">
        {#each $photos_to_left as photo}
            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>
                {#if photo.sizes && photo.sizes[50]}
                    <img src={photo.sizes[50].url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>
                {/if}
            </div>
        {/each}
    </div>

    <div class="photo-container" bind:clientWidth >
        {#if $photo_to_left}
            <Photo photo={$photo_to_left} className="left" />
        {/if}
        {#if $photo_in_front}
            <Photo photo={$photo_in_front} className="front" {clientWidth} />
        {/if}
        {#if $photo_to_right}
            <Photo photo={$photo_to_right} className="right" />
        {/if}
    </div>

    <div class="thumbnails-bottom">
        {#each reversed($photos_to_right) as photo}
            <div class="thumbnail" on:click={() => handleThumbnailClick(photo)} role="button" tabindex="0" on:keydown={e => e.key === 'Enter' && handleThumbnailClick(photo)}>
                {#if photo.sizes && photo.sizes[50]}
                    <img src={photo.sizes[50].url} alt="Thumbnail" style="border-color: {photo.bearing_color || '#ccc'}"/>
                {/if}
            </div>
        {/each}
    </div>

    {#if $app.debug === 1}
        <div class="debug">
            <b>Debug Information</b><br>
            <b>Bearing:</b>  {$bearing}<br>
            <b>Pos.center:</b> {$pos.center}<br>
            <b>Left:</b>  {$photo_to_left?.file}<br>
            <b>Front:</b> {$photo_in_front?.file}<br>
            <b>Right:</b>  {$photo_to_right?.file}<br>
            <b>Photos in area:</b> {$photos_in_area.length}<br>
            <b>Range:</b> {$pos2.range / 1000} km<br>
            <b>Photos in range count:</b> {$photos_in_range.length}<br>
            <b>Photos in range:</b>
            <ul>
            {#each $photos_in_range as photo}
                <li>{photo.id},{photo.file}</li>
            {/each}
                </ul>
            <b>Photos to left:</b>
            {JSON.stringify($photos_to_left, null, 2)}
<!--            <ul>-->
<!--            {#each $photos_to_left as photo}-->
<!--                <li>{photo.id},{photo.file}-->
<!--                    {JSON.stringify(photo.sizes, null, 2)}-->
<!--                </li>-->
<!--            {/each}-->
<!--            </ul>-->
            <b>Photos to right:</b>
            <ul>
            {#each $photos_to_right as photo}
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
