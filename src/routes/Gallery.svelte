<script>
    import {
        app,
        pos,
        bearing,
        photos_in_area,
        photos_in_range,
        photo_in_front,
        photo_to_left,
        photo_to_right,
        update_bearing,
        turn_to_photo_to
    } from "$lib/data.svelte.js";
    import {dms} from "$lib/utils.js";
</script>

<div class="photo-container">
    {#if $photo_to_left}
        <img src={$photo_to_left.url} alt={$photo_to_left.file} class="photo left"/>
    {/if}
    {#if $photo_in_front}
        <img src={$photo_in_front.url} alt={$photo_in_front.file} class="photo front" fetchpriority="high" />
    {/if}
    {#if $photo_to_right}
        <img src={$photo_to_right.url} alt={$photo_to_right.file} class="photo right"/>
    {/if}

    {#if $app.debug}
        <div class="debug">
            <b>Debug Information</b><br>
            <b>Bearing:</b>  {$bearing}<br>
            <b>Pos.center:</b> {$pos.center}<br>
            <b>Left:</b>  {$photo_to_left.file}<br>
            <b>Front:</b> {$photo_in_front.file}<br>
            <b>Right:</b>  {$photo_to_right.file}<br>
            <b>Photos in area:</b> {$photos_in_area.length}<br>
            <b>Range:</b> {$pos.range} km<br>
            <b>Photos in range count:</b> {$photos_in_range.length}<br>
            <b>Photos in range:</b>
            <ul>
            {#each $photos_in_range as photo}
                <li>{photo.file}</li>
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
    .photo-container {
        border: 1px solid black;
        position: relative;
        width: 100%;
        height: 100%; /* fills the parent's height */
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    .photo {
        display: block;
        border: 1px solid green;
        max-width: 100%;
        max-height: 100%;
        object-fit: contain; /* This ensures aspect ratio is maintained */
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

    }

    .right {
        opacity: 0.4;
        position: absolute;
        top: 50%;
        transform: translateY(-20%);
        z-index: 1;
        /* Optionally, set a width to control how much of the side image shows */
        width: 90%;
    }

    /* Left image: fade out from fully opaque at the left edge to transparent toward the center */
    .left {
        left: 0;
        mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to right, white 0%, white 70%, transparent 100%);
    }

    /* Right image: fade out from fully opaque at the right edge to transparent toward the center */
    .right {
        right: 0;
        mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
        -webkit-mask-image: linear-gradient(to left, white 0%, white 70%, transparent 100%);
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

    ul {
        margin: 0.3em;
    }
</style>
