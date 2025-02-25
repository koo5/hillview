<script>
    import { onMount, onDestroy } from 'svelte';
    import { Map, TileLayer, Marker, Circle } from 'svelte-leaflet';
    import { RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle } from 'lucide-svelte';
    import L from 'leaflet';

    import {
        center,
        zoom,
        range,
        bearing,
        top_left,
        bottom_right,

        photos,
        photos_in_area,
        photos_in_range,
        photo_to_left,
        photo_to_right,

        turn_to_photo_to, photo_in_front
    } from "$lib/data.svelte.js";
    import {Coordinate} from "tsgeo/Coordinate";


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
    function get_range(center) {
        const pointC = map.latLngToContainerPoint(center);
        // Move 100px to the right
        const pointR = L.point(pointC.x + fov_circle_radius_px, pointC.y);
        const latLngR = map.containerPointToLatLng(pointR);
        // distanceTo returns meters
        return center.distanceTo(latLngR) / 1000;
    }

    // Update local mapState and notify parent
    function updateMapState() {
        if (!map) return;
        let _center = map.getCenter();
        //center = new Coordinate(_center.lat, _center.lng);
        //zoom = map.getZoom();
        range = get_range(center);
        top_left = map.getBounds().getNorthWest();
        bottom_right = map.getBounds().getSouthEast();
    }


    // Listen for arrow keys
    function handleKeyDown(e) {
        if (e.key === 'z') {
            bearing -=5;
        } else if (e.key === 'x') {
            bearing +=5;
        }
    }

    onMount(() => {
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

    $: arrow_radians = (bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;

    // Helper for coloring the marker icons
    function getColor(photo) {
        if (photo.abs_bearing_diff === null) return '#9E9E9E'; // grey
        function rgbToHex(r,g,b) {
            return '#' + [r,g,b].map(x => {
                const hex = x.toString(16);
                return hex.length === 1 ? '0' + hex : hex;
            }).join('');
        }
        return rgbToHex(photo.abs_bearing_diff, 255 - photo.abs_bearing_diff, 0);
    }
</script>


<!-- The map container -->
<div class="relative w-full h-full">
    <!--
      We bind the Leaflet map instance to the variable `map` using `bind:leafletMap`.
      This gives us direct access to the underlying L.Map object for bounding, etc.
    -->
    <Map
            center={center}
            zoom={zoom}
            style="width: 100%; height: 100%;"
            bind:leafletMap={map}
            on:moveend={updateMapState}
            on:zoomend={updateMapState}
    >
        <!-- Base map tiles -->
        <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                attribution="&copy; OpenStreetMap contributors"
        />

        <!-- Visibility Circle (maxDistance in km, Circle wants meters) -->
        <Circle
                latLng={center}
                radius={range}
                color="#4A90E2"
                fillColor="#4A90E2"
                fillOpacity={0.07}
                weight={0.8}
        />

        <!-- Markers for photos -->
        {#each photos_in_area as photo (photo.id)}
                <Marker
                        latLng={[photo.latitude, photo.longitude]}
                        icon={createDirectionalArrow(photo.direction, getColor(photo))}
                        title={`Photo at ${photo.latitude.toFixed(6)}, ${photo.longitude.toFixed(6)}\n
Direction: ${photo.direction.toFixed(1)}°\n
(Relative: ${(photo.direction - bearing).toFixed(1)}°)`}
                />

        {/each}
    </Map>

    <!-- FOV Overlay (the arrow & circle in the center of the screen) -->
    <div class="absolute inset-0 pointer-events-none" style="z-index: 30000;">
        <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <svg
                    width={width}
                    height={height}
                    viewBox={`0 0 ${width} ${height}`}
                    class="transition-transform duration-200"
            >
                <!-- Outer circle -->
                <circle
                        cx={centerX}
                        cy={centerY}
                        r={radius}
                        fill="rgba(74, 144, 226, 0.1)"
                        stroke="rgb(74, 144, 226)"
                        stroke-width="2"
                />

                <!-- Direction arrow line -->
                <line
                        x1={centerX}
                        y1={centerY}
                        x2={arrowX}
                        y2={arrowY}
                        stroke="rgb(74, 144, 226)"
                        stroke-width="3"
                        marker-end="url(#arrowhead)"
                />

                <!-- Arrow head -->
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

                <!-- Center dot -->
                <circle
                        cx={centerX}
                        cy={centerY}
                        r="3"
                        fill="rgb(74, 144, 226)"
                />
            </svg>
        </div>
    </div>

    <!-- Rotation / navigation buttons -->
    <div class="absolute bottom-4 left-4 flex gap-2" style="z-index: 30000;">
        <button
                on:click={() => rotateToNextPhoto('left')}
                class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
                title="Rotate to next photo on the left"
        >
            <ArrowLeftCircle class="w-5 h-5 text-gray-700" />
        </button>

        <button
                on:click={() => rotateBearing(-15)}
                class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
                title="Rotate view 15° counterclockwise"
        >
            <RotateCcw class="w-5 h-5 text-gray-700" />
        </button>

        <button
                on:click={() => rotateBearing(15)}
                class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
                title="Rotate view 15° clockwise"
        >
            <RotateCw class="w-5 h-5 text-gray-700" />
        </button>

        <button
                on:click={() => rotateToNextPhoto('right')}
                class="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
                title="Rotate to next photo on the right"
        >
            <ArrowRightCircle class="w-5 h-5 text-gray-700" />
        </button>
    </div>

    <!-- Small help text -->
    <div class="absolute bottom-4 right-4 bg-white p-2 rounded shadow" style="z-index: 30000;">
        <p class="text-sm">Use ← → arrow keys or buttons to rotate the view direction.</p>
    </div>
</div>
