<script>
    import {photos_in_range, photo_to_left, photo_in_front, photo_to_right} from "$lib/data.svelte.js";
</script>

<div>
    <h3 >{$photos_in_range.length} photos</h3>
</div>

<div>
    {#if $photo_to_left}
        <img src={$photo_to_left.url} alt={$photo_to_left.file} class="photo left"/>
    {/if}
    {#if $photo_in_front}
        <img src={$photo_in_front.url} alt={$photo_in_front.file} class="photo front"/>
    {/if}
    {#if $photo_to_right}
        <img src={$photo_to_right.url} alt={$photo_to_right.file} class="photo right"/>
    {/if}

</div>


<style>
    .photo {
        max-width: 80%;
        max-height: 80%;
    }

    .left {
        left: 0;
        opacity: 0.5;
    }

    .front {
    }

    .right {
        right: 0;
        opacity: 0.5;
    }
</style>