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
    } from "$lib/data.svelte.ts";
    import {dms} from "$lib/utils.ts";
    import Photo from "./Photo.svelte";
</script>

<div class="photo-container">
    {#if $photo_to_left}
        <Photo photo={$photo_to_left} className="left" />
    {/if}
    {#if $photo_in_front}
        <Photo photo={$photo_in_front} className="front" />
    {/if}
    {#if $photo_to_right}
        <Photo photo={$photo_to_right} className="right" />
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
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
    }

    ul {
        margin: 0.3em;
    }
</style>
