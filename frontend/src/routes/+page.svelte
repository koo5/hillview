<script>
    import {onDestroy, onMount} from 'svelte';
    import PhotoGallery from '../components/Gallery.svelte';
    import Map from '../components/Map.svelte';
    import {Camera, Compass} from 'lucide-svelte';
    import {fetch_photos} from "$lib/sources.js";
    import {dms} from "$lib/utils.js";
    import {goto} from "$app/navigation";
    import {app, turn_to_photo_to, update_bearing} from "$lib/data.svelte.js";

    onMount(async () => {
        await fetch_photos();
        window.addEventListener('keydown', handleKeyDown);
    });
    onDestroy(() => {
        window.removeEventListener('keydown', handleKeyDown);
    });

    async function handleKeyDown(e) {
        if (e.key === 'z') {
            update_bearing(-5);
        } else if (e.key === 'x') {
            update_bearing(5);
        } else if (e.key === 'c') {
            await turn_to_photo_to('left');
        } else if (e.key === 'v') {
            await turn_to_photo_to('right');
        }
        else if (e.key === 'd') {
            app.update(a => {
                a.debug = a.debug + 1;
                if (a.debug > 2) {
                    a.debug = 0;
                }
                return a;
            });
        }
    }

    let menuOpen = false;
    const toggleMenu = () => {
        menuOpen = !menuOpen;
    }

    let debugOpen = false;
    const toggleDebug = () => {
        app.update(a => {
            a.debug = !a.debug;
            return a;
        });
    }
</script>

<!-- Hamburger icon -->
<!--<div class="hamburger" on:click={toggleMenu}>-->
<!--    <div class="bar"></div>-->
<!--    <div class="bar"></div>-->
<!--    <div class="bar"></div>-->
<!--</div>-->


{#if menuOpen}
    <nav class="nav-menu">
        <ul>
            <li><a href="/">Map</a></li>
            <li><a href="/upload">Sources</a></li>
            <li><a href="/about">About</a></li>
        </ul>
    </nav>
{/if}

{#if debugOpen}
{/if}

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
    :global(*) {
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


    .hamburger {
        width: 30px;
        height: 25px;
        display: flex;
        position: absolute;
        flex-direction: column;
        justify-content: space-between;
        cursor: pointer;
        z-index: 30000;
    }

    .bar {
        z-index: 30000;
        height: 3px;
        background-color: #333;
        border-radius: 3px;
    }

    .nav-menu {
        z-index: 30000;
        background: #f5f5f5;
        position: absolute;
        top: 30px;
        left: 0px;
        width: 200px;
        padding: 1rem;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .nav-menu ul {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .nav-menu li {
        margin-bottom: 0.5rem;
        font-size: 2rem;
    }

    .nav-menu li a {
        text-decoration: none;
        color: #333;
    }

    .debug-button {
        position: absolute;
        height: 25px;
        top: 0px;
        left: 50px;
        align-content: center;
        cursor: pointer;
        z-index: 50000;
        border: 1px solid black;
    }
</style>
