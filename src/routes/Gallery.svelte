<script>
    import { photos_in_range, photo_to_left, photo_in_front, photo_to_right } from "$lib/data.svelte.js";
</script>

<div class="photo-container">
    {#if $photo_to_left}
        <img src={$photo_to_left.url} alt={$photo_to_left.file} class="photo left" />
    {/if}
    {#if $photo_in_front}
        <img src={$photo_in_front.url} alt={$photo_in_front.file} class="photo front" />
    {/if}
    {#if $photo_to_right}
        <img src={$photo_to_right.url} alt={$photo_to_right.file} class="photo right" />
    {/if}
</div>

<style>
    .photo-container {
        position: relative;
        width: 100%;
        height: 100%;
        overflow: hidden;
        align-items: center; /* centers the front image vertically */
        justify-content: center; /* centers the front image horizontally */
    }

    .photo {
        display: block;
    }

    /* Center the front image at 80% of the container */
    .front {
        width: 95%;
        margin: 0 auto;
        position: relative;
        z-index: 2;
    }

    /* Side photos: smaller, positioned absolutely, with only their edges visible */
    .left,
    .right {
        position: absolute;
        height: 100%;
        z-index: 1;
        opacity: 0.2;
    }

    /* Push the left photo mostly off the left side */
    .left {
        left: -20%;
    }

    /* Push the right photo mostly off the right side */
    .right {
        right: -20%;
    }
</style>
