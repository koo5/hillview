<script>
    import {onDestroy, onMount, tick} from 'svelte';
    import PhotoGallery from '../components/Gallery.svelte';
    import Map from '../components/Map.svelte';
    import {Camera, Compass} from 'lucide-svelte';
    import {fetch_photos} from "$lib/sources.js";
    import {dms} from "$lib/utils.js";
    import {app, pos, bearing, turn_to_photo_to, update_bearing, update_pos} from "$lib/data.svelte.js";
    import {LatLng} from 'leaflet';
    import { goto, replaceState } from "$app/navigation";
    import {get, writable} from "svelte/store";

    let map = null;
    let update_url = false;

    onMount(async () => {
        console.log('Page mounted');
        await tick();

        const urlParams = new URLSearchParams(window.location.search);
        const lat = urlParams.get('lat');
        const lon = urlParams.get('lon');
        const zoom = urlParams.get('zoom');
        const bearingParam = urlParams.get('bearing');

        let p = get(pos);
        let update = false;

        if (lat && lon) {
            console.log('Setting position to', lat, lon, 'from URL');
            p.center = new LatLng(parseFloat(lat), parseFloat(lon));
            update = true;
        }

        if (zoom) {
            console.log('Setting zoom to', zoom, 'from URL');
            p.zoom = parseFloat(zoom);
            update = true;
        }

        if (update) {
            update_pos((v) => {return {...p, reason: 'url'}});
            map?.setView(p.center, p.zoom);
        }

        if (bearingParam) {
            console.log('Setting bearing to', bearingParam, 'from URL');
            bearing.set(parseFloat(bearingParam));
        }

        await fetch_photos();
        window.addEventListener('keydown', handleKeyDown);

        setTimeout(() => {
            update_url = true;
        }, 100);

    });

    pos.subscribe(p => {
        if (!update_url) {
            return;
        }
        const url = new URL(window.location);
        url.searchParams.set('lat', p.center.lat);
        url.searchParams.set('lon', p.center.lng);
        url.searchParams.set('zoom', p.zoom);
        console.log('Setting URL to', url.toString());
        replaceState2(url.toString());
    });

    bearing.subscribe(b => {
        if (!update_url) {
            return;
        }
        const url = new URL(window.location);
        url.searchParams.set('bearing', b);
        console.log('Setting URL to', url.toString());
        setTimeout(() => {
            replaceState2(url.toString());
        }, 1000);
    });

    let desiredUrl = null;

    function replaceState2(url) {
        desiredUrl = url;
        try {
            replaceState(url);
        } catch (e) {
            console.error('Failed to update URL', e);
            setTimeout(() => {
                replaceState(desiredUrl);
            }, 1000);
        }
    }

    onDestroy(() => {
        console.log('Page destroyed');
        window.removeEventListener('keydown', handleKeyDown);
    });

    async function handleKeyDown(e) {
        if (!e.ctrlKey && !e.altKey && !e.metaKey) {
            if (e.key === 'z') {
                e.preventDefault();
                update_bearing(-5);
            } else if (e.key === 'x') {
                e.preventDefault();
                update_bearing(5);
            } else if (e.key === 'c') {
                e.preventDefault();
                await turn_to_photo_to('left');
            } else if (e.key === 'v') {
                e.preventDefault();
                await turn_to_photo_to('right');
            } else if (e.key === 'd') {
                e.preventDefault();
                app.update(a => {
                    a.debug = a.debug + 1;
                    if (a.debug > 2) {
                        a.debug = 0;
                    }
                    return a;
                });
            }
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

<div class="container">
    <div class="panel">
        <PhotoGallery/>
    </div>
    <div class="panel">
        <Map bind:this={map}/>
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

</style>
