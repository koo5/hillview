<script lang="ts">
    import {onMount, onDestroy} from 'svelte';
    import {Polygon, LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle} from 'lucide-svelte';
    import L from 'leaflet';
    import {Coordinate} from "tsgeo/Coordinate";
    import 'leaflet/dist/leaflet.css';

    import {pos, bearing, photos_in_area, update_bearing, turn_to_photo_to} from "$lib/data.svelte.js";


    let map;
    let _map;
    const fov_circle_radius_px = 200;

    // Create the directional arrow icon for each photo
    function createDirectionalArrow(bearing, color) {
        console.log('createDirectionalArrow', bearing, color);
        bearing = Math.round(bearing);
        //color = '#4A90E2';
        const svg = `
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
           xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10"
                fill="${color}" fill-opacity="0.2"
                stroke="${color}" stroke-width="2"
                 />
        <path transform="rotate(${bearing} 12 12)"
              d="M12 6l4 6h-8z"
              fill="${color}" />
      </svg>
    `;
        return L.divIcon({
            className: 'photo-direction-arrow',
            html: svg,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });
    }

    function RGB2HTML(red, green, blue)
    {
        red = Math.min(255, Math.max(0, Math.round(red)));
        green = Math.min(255, Math.max(0, Math.round(green)));
        blue = Math.min(255, Math.max(0, Math.round(blue)));
        let r = red.toString(16);
        let g = green.toString(16);
        let b = blue.toString(16);
        if (r.length == 1) r = '0' + r;
        if (g.length == 1) g = '0' + g;
        if (b.length == 1) b = '0' + b;
        return '#' + r + g + b;
    }
    // Helper for coloring the marker icons
    function getColor(photo) {
        if (photo.abs_bearing_diff === null) return '#9E9E9E'; // grey
        return RGB2HTML(photo.abs_bearing_diff, 255 - photo.abs_bearing_diff, 0);
    }

    // Calculate how many km are “visible” based on the current zoom/center
    function get_range(_center: LatLng) {
        const pointC = map.latLngToContainerPoint(_center);
        // Move 100px to the right
        const pointR = L.point(pointC.x + fov_circle_radius_px, pointC.y);
        const latLngR = map.containerPointToLatLng(pointR);
        // distanceTo returns meters
        return _center.distanceTo(latLngR) / 1000;
    }

    // Update local mapState and notify parent
    function updateMapState() {
        console.log('updateMapState');
        let _center = map.getCenter();
        pos.update((value) => {
            return {
                ...value,
                center: new Coordinate(_center.lat, _center.lng),
                zoom: map.getZoom(),
                range: get_range(_center),
                top_left: map.getBounds().getNorthWest(),
                bottom_right: map.getBounds().getSouthEast()
            };
        });
    }


    // Listen for arrow keys
    function handleKeyDown(e) {
        if (e.key === 'z') {
            update_bearing(-5);
        } else if (e.key === 'x') {
            update_bearing(5);
        } else if (e.key === 'c') {
            turn_to_photo_to('left');
        } else if (e.key === 'v') {
            turn_to_photo_to('right');
        }
    }

    onMount(() => {
        map = _map.getMap();
        updateMapState();
        window.addEventListener('keydown', handleKeyDown);
    });
    onDestroy(() => {
        window.removeEventListener('keydown', handleKeyDown);
    });


    let width;
    let height;

    // For the bearing overlay arrow:
    let centerX;
    $: centerX = width / 2;
    let centerY;
    $: centerY = height / 2;
    let arrowLength = fov_circle_radius_px - 20;

    let arrow_radians;
    let arrowX;
    let arrowY;

    $: arrow_radians = ($bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;



    const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

</script>


<!-- The map container -->
<div class="map" bind:clientWidth={width} bind:clientHeight={height}>
    <LeafletMap
            bind:this={_map}
            options={{center: [$pos.center.lat, $pos.center.lng], zoom: $pos.zoom}}
            events={{moveend: updateMapState, zoomend: updateMapState}}
    >

        <ScaleControl position="bottomleft" options={{maxWidth: 500}}/>

        <!-- Base map tiles -->
        <TileLayer
                url={tileUrl}
                options={{
                    maxZoom: 30,
                    }}
                attribution="&copy; OpenStreetMap contributors"
        />

        <!-- Visibility Circle (maxDistance in km, Circle wants meters) -->
        {#if $pos.center}
            <Circle
                    latLng={$pos.center}
                    radius={$pos.range * 1000}
                    color="#4A90E2"
                    fillColor="#4A90E2"
                    weight={1.8}
            />
            <!-- arrow -->
        {/if}

        <!-- Markers for photos -->
        {#each $photos_in_area as photo (photo.file)}
            <Marker
                    latLng={photo.coord}
                    icon={createDirectionalArrow(photo.bearing, getColor(photo))}
                    title={`Photo at ${photo.coord.lat.toFixed(6)}, ${photo.coord.lng.toFixed(6)}\n
Direction: ${photo.bearing.toFixed(1)}°\n
(Relative: ${(photo.bearing - $bearing).toFixed(1)}°)`}
            />

        {/each}

        <div class="svg-overlay">
            <svg
                    width={width}
                    height={height}
                    viewBox={`0 0 ${width} ${height}`}
            >
                <!--                    <circle-->
                <!--                            cx={centerX}-->
                <!--                            cy={centerY}-->
                <!--                            r={radius}-->
                <!--                            fill="rgba(74, 144, 226, 0.1)"-->
                <!--                            stroke="rgb(74, 144, 226)"-->
                <!--                            strokeWidth="2"-->
                <!--                    />-->

                <line
                        x1={centerX}
                        y1={centerY}
                        x2={arrowX}
                        y2={arrowY}
                        stroke="rgb(74, 144, 226)"
                        stroke-width="3"
                        marker-end="url(#arrowhead)"
                />
                <defs>
                    <marker
                            id="arrowhead"
                            markerWidth="10"
                            markerHeight="7"
                            refX="9"
                            refY="3.5"
                            orient="auto"
                    >
                        <polygon
                                points="0 0, 10 3.5, 0 7"
                                fill="rgb(74, 144, 226)"
                        />
                    </marker>
                </defs>

                <!--                    <circle-->
                <!--                            cx={centerX}-->
                <!--                            cy={centerY}-->
                <!--                            r="3"-->
                <!--                            fill="rgb(74, 144, 226)"-->
                <!--                    />-->
            </svg>
        </div>


    </LeafletMap>

</div>

<!-- Rotation / navigation buttons -->
<div class="absolute bottom-4 left-4 flex gap-2" style="z-index: 30000;">
    <button
            on:click={() => turn_to_photo_to('left')}
            class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
            title="Rotate to next photo on the left"
    >
        <ArrowLeftCircle class="w-5 h-5 text-gray-700"/>
    </button>

    <button
            on:click={() => update_bearing(-15)}
            class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
            title="Rotate view 15° counterclockwise"
    >
        <RotateCcw class="w-5 h-5 text-gray-700"/>
    </button>

    <button
            on:click={() => update_bearing(15)}
            class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
            title="Rotate view 15° clockwise"
    >
        <RotateCw class="w-5 h-5 text-gray-700"/>
    </button>

    <button
            on:click={() => turn_to_photo_to('right')}
            class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
            title="Rotate to next photo on the right"
    >
        <ArrowRightCircle class="w-5 h-5 text-gray-700"/>
    </button>
</div>

<!-- Small help text -->
<div class="absolute bottom-4 right-4 bg-white p-2 rounded shadow" style="z-index: 30000;">
    <p class="text-sm">Use ← → arrow keys or buttons to rotate the view direction.</p>
</div>

width: {width}, height: {height}
centerX: {centerX}, centerY: {centerY}
arrowX: {arrowX}, arrowY: {arrowY}

<style>
    .map {
        width: 500px;
        height: 500px;
    }

    .svg-overlay {
        position: absolute;
        top: 0;
        left: 0;
        z-index: 30000;
    }

</style>