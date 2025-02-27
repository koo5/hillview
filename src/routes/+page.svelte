<script>
    import {onMount} from 'svelte';
    import PhotoGallery from './Gallery.svelte';
    import Map from './Map.svelte';
    import {Camera, Compass} from 'lucide-svelte';

    import {app, pos, bearing} from "$lib/data.svelte.js";
    import {fetch_photos} from "$lib/sources.js";
    import {dms} from "$lib/utils.js";
    import {goto} from "$app/navigation";

    onMount(async () => {
        await fetch_photos();
    });
</script>

<div class="container">
    <div class="panel">
        <PhotoGallery/>
    </div>
    <div class="panel">
        <Map/>
    </div>
</div>

<style>
    /* Reset default margin, padding and prevent body scroll */
    :global(html, body) {
        margin: 0;
        padding: 0;
        overflow: hidden;
        width: 100%;
        height: 100%;
    }

    /* Ensure padding and borders are included in the elements' total size */
    :global(*){
        box-sizing: border-box;
    }

    /* Container occupies the full viewport */
    .container {
        display: flex;
        width: 100vw;
        height: 100vh;
        flex-direction: row; /* Default landscape mode */
    }

    /* Each panel takes up equal space */
    .panel {
        flex: 1;
        overflow: auto;
    }

    /* For portrait mode, stack panels vertically */
    @media (orientation: portrait) {
        .container {
            flex-direction: column;
        }
    }
</style>
