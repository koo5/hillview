<script lang="ts">
    import {onMount, onDestroy} from 'svelte';
    import {LeafletMap, TileLayer, Marker, Circle } from 'svelte-leafletjs';
    import { LatLng } from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle} from 'lucide-svelte';
    import L from 'leaflet';
    import {Coordinate} from "tsgeo/Coordinate";
    import 'leaflet/dist/leaflet.css';

    import {map_state, data, turn_to_photo_to} from "$lib/data.svelte.js";


    let map;
    let _map;
    const fov_circle_radius_px = 200;

    // Create the directional arrow icon for each photo
    function createDirectionalArrow(direction, color) {
        const svg = `
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none"
           xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10"
                fill="${color}" fill-opacity="0.2"
                stroke="${color}" stroke-width="2" />
        <path transform="rotate(${direction} 12 12)"
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
        map_state.center = new LatLng(_center.lat, _center.lng);
        map_state.zoom = map.getZoom();
        map_state.range = get_range(map_state.center);
        map_state.top_left = map.getBounds().getNorthWest();
        map_state.bottom_right = map.getBounds().getSouthEast();
    }


    // Listen for arrow keys
    function handleKeyDown(e) {
        if (e.key === 'z') {
            map_state.bearing -= 5;
        } else if (e.key === 'x') {
            map_state.bearing += 5;
        }
    }

    onMount(() => {
        map = _map.getMap();
        window.addEventListener('keydown', handleKeyDown);
    });
    onDestroy(() => {
        window.removeEventListener('keydown', handleKeyDown);
    });

    // For the “Field of View” overlay arrow:

    const width = 400;
    const height = 400;

    const centerX = width / 2;
    const centerY = height / 2;
    const arrowLength = fov_circle_radius_px - 20;

    let arrow_radians;
    let arrowX;
    let arrowY;

    $: arrow_radians = (map_state.bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;

    // Helper for coloring the marker icons
    function getColor(photo) {
        if (photo.abs_bearing_diff === null) return '#9E9E9E'; // grey
        function rgbToHex(r, g, b) {
            return '#' + [r, g, b].map(x => {
                const hex = x.toString(16);
                return hex.length === 1 ? '0' + hex : hex;
            }).join('');
        }

        return rgbToHex(photo.abs_bearing_diff, 255 - photo.abs_bearing_diff, 0);
    }

    const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";


</script>


<!-- The map container -->
<div class="map">
    <LeafletMap
            bind:this={_map}
            options={{center: [map_state.center.lat, map_state.center.lng], zoom: map_state.zoom}}
            events={{moveend: updateMapState, zoomend: updateMapState}}
    >
    <!-- Base map tiles -->
    <TileLayer
            url={tileUrl}
            options={{
                    maxZoom: 18,
                    }}
            attribution="&copy; OpenStreetMap contributors"
    />

    <!-- Visibility Circle (maxDistance in km, Circle wants meters) -->
    {#if map_state.center}
        <!--            <Circle-->
        <!--                    latLng={[map_state.center.lat, map_state.center.lng]}-->
        <!--                    radius={map_state.range * 1000}-->
        <!--                    color="#4A90E2"-->
        <!--                    fillColor="#4A90E2"-->
        <!--                    fillOpacity={0.07}-->
        <!--                    weight={0.8}-->
        <!--            />-->
    {/if}

    <!-- Markers for photos -->
    {#each data.photos_in_area as photo (photo.id)}
        <Marker
                latLng={[photo.latitude, photo.longitude]}
                icon={createDirectionalArrow(photo.direction, getColor(photo))}
                title={`Photo at ${photo.latitude.toFixed(6)}, ${photo.longitude.toFixed(6)}\n
Direction: ${photo.direction.toFixed(1)}°\n
(Relative: ${(photo.direction - map_state.bearing).toFixed(1)}°)`}
        />

    {/each}
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
            on:click={() => map_state.bearing -=15}
            class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
            title="Rotate view 15° counterclockwise"
    >
        <RotateCcw class="w-5 h-5 text-gray-700"/>
    </button>

    <button
            on:click={() => map_state.bearing +=15}
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

<style>
    .map {
        width: 500px;
        height: 500px;
    }

</style>