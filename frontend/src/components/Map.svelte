<script lang="ts">
    import {onMount, onDestroy, tick} from 'svelte';
    import {Polygon, LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle} from 'lucide-svelte';
    import L from 'leaflet';
    import {Coordinate} from "tsgeo/Coordinate";
    import 'leaflet/dist/leaflet.css';

    import {
        app,
        pos,
        pos2,
        bearing,
        photos_in_area,
        photo_in_front,
        photo_to_left,
        photo_to_right,
        update_bearing,
        turn_to_photo_to
    } from "$lib/data.svelte.js";
    import {get} from "svelte/store";


    let map;
    let _map;
    const fov_circle_radius_px = 70;

    function createDirectionalArrow(photo) {
        let bearing = Math.round(photo.bearing);
        let color = '#000';
        let arrow_color = color;
        let size = 100;
        let inner_size = $pos.zoom * 3;
        let outer_size = 100;
        /*if ($photo_to_left === photo || $photo_to_right === photo) {
            size = 55;
            //arrow_color = '#88f';
        } else*/
        let dashes = '';
        let fill = '';
        let stroke_width = 1;
        if ($photo_in_front === photo) {
            //dashes = 'stroke-dasharray="20 4"'
            dashes = 'stroke-dasharray="1 10"'
            color = photo.bearing_color;
            fill = `fill="${color}"`;
            stroke_width = 6
            //arrow_color = 'blue';
        }
        const half = Math.round(size / 2);

        // Define arrow dimensions relative to the size.
        // Adjust these variables to easily control the arrow's shape.
        const arrowTipY_inner = inner_size * 0.1;      // Y coordinate for the arrow tip (top)
        const arrowBaseY_inner = inner_size * 0.8;    // Y coordinate for the arrow base
        const arrowWidth_inner = inner_size * 0.15;    // Horizontal offset from center (controls thinness)
        const arrowTipY_outer = outer_size * 0.1;
        const arrowBaseY_outer = inner_size * 0.80;
        const arrowWidth_outer = outer_size * 0.15;

        let svg = `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" fill="none"
         xmlns="http://www.w3.org/2000/svg">
      <polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_inner}
                 ${half + arrowWidth_inner},${arrowBaseY_inner}
                 ${half - arrowWidth_inner},${arrowBaseY_inner}"
                 ${fill} fill-opacity=0.8
               stroke="#000" stroke-width="1" />`

        if (photo === $photo_in_front) {
            svg += `
      <polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_outer}
                 ${half + arrowWidth_outer},${arrowBaseY_outer}
                 ${half - arrowWidth_outer},${arrowBaseY_outer}"

               stroke="${color}" stroke-linecap="round" stroke-width="${stroke_width}" ${dashes}  />
    </svg>
  `;
        }

        return L.divIcon({
            className: 'photo-direction-arrow',
            html: svg,
            iconSize: [size, size],
            iconAnchor: [half, half]
        });
    }

    // Calculate how many km are "visible" based on the current zoom/center
    function get_range(_center: LatLng) {
        const pointC = map.latLngToContainerPoint(_center);
        // Move 100px to the right
        const pointR = L.point(pointC.x + fov_circle_radius_px, pointC.y);
        const latLngR = map.containerPointToLatLng(pointR);
        // distanceTo returns meters
        return _center.distanceTo(latLngR);
    }

    // Update local mapState and notify parent
    async function updateMapState(force) {
        await tick();
        let _center = map.getCenter();
        console.log('updateMapState center:', _center, 'map.getZoom():', map.getZoom());
        let p = get(pos);
        let new_v = {
            ...p,
            center: new Coordinate(_center.lat, _center.lng),
            zoom: map.getZoom(),
        };
        if (force === true || p.center.lat !== new_v.center.lat || p.center.lng !== new_v.center.lng || p.zoom !== new_v.zoom) {
            pos.update((value) => {
                return new_v;
            });
            pos2.update((value) => {
                return {
                    ...value,
                    range: get_range(_center),
                    top_left: map.getBounds().getNorthWest(),
                    bottom_right: map.getBounds().getSouthEast()
                };
            });
        }

    }

    // Handle button clicks and prevent map interaction
    function handleButtonClick(action, event) {
        event.preventDefault();
        event.stopPropagation();

        if (action === 'left') {
            turn_to_photo_to('left');
        } else if (action === 'right') {
            turn_to_photo_to('right');
        } else if (action === 'rotate-ccw') {
            update_bearing(-15);
        } else if (action === 'rotate-cw') {
            update_bearing(15);
        }

        return false;
    }

    onMount(async () => {
        map = _map.getMap();
        await updateMapState(true);
    });

    let width;
    let height;

    // For the bearing overlay arrow:
    let centerX;
    $: centerX = width / 2;
    let centerY;
    $: centerY = height / 2;
    let arrowLength = fov_circle_radius_px + 150;

    let arrow_radians;
    let arrowX;
    let arrowY;

    $: arrow_radians = ($bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;

    const tileUrl = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";

</script>


<!-- The map container -->
<div bind:clientHeight={height} bind:clientWidth={width} class="map">
    <LeafletMap
            bind:this={_map}
            events={{moveend: updateMapState, zoomend: updateMapState}}
            options={{center: [$pos.center.lat, $pos.center.lng], zoom: $pos.zoom}}
    >

        <ScaleControl options={{maxWidth: 100}} position="bottomleft"/>

        <!-- Base map tiles -->
        <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                options={{
                    maxZoom: 23,
                    maxNativeZoom: 19,
                    }}
                url={tileUrl}
        />


        {#if $pos.center}
            <Circle
                    latLng={$pos.center}
                    radius={$pos2.range}
                    color="#4AE092"
                    fillColor="#4A90E2"
                    weight={1.8}
            />
            <!-- arrow -->
        {/if}

        <!-- Markers for photos -->
        {#each $photos_in_area as photo (photo.id)}
            <Marker
                    zIndexOffset={10000*180-photo.abs_bearing_diff*10000}
                    latLng={photo.coord}
                    icon={createDirectionalArrow(photo)}
                    title={`Photo at ${photo.coord.lat.toFixed(6)}, ${photo.coord.lng.toFixed(6)}\n
Direction: ${photo.bearing.toFixed(1)}°\n
(Relative: ${(photo.bearing - $bearing).toFixed(1)}°)`}
            />

        {/each}

        <div class="svg-overlay">
            <svg
                    height={height}
                    viewBox={`0 0 ${width} ${height}`}
                    width={width}
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
                        marker-end="url(#arrowhead)"
                        stroke="rgb(74, 144, 226)"
                        stroke-width="3"
                        x1={centerX}
                        x2={arrowX}
                        y1={centerY}
                        y2={arrowY}
                />
                <defs>
                    <marker
                            id="arrowhead"
                            markerHeight="7"
                            markerWidth="10"
                            orient="auto"
                            refX="9"
                            refY="3.5"
                    >
                        <polygon
                                fill="rgb(74, 244, 74)"
                                points="0 0, 10 3.5, 0 7"
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
<div class="control-buttons-container">
    <div class="buttons" role="group">
        <button
                on:click={(e) => handleButtonClick('left', e)}
                title="Rotate to next photo on the left"
        >
            <ArrowLeftCircle/>
        </button>

        <button
                on:click={(e) => handleButtonClick('rotate-ccw', e)}
                title="Rotate view 15° counterclockwise"
        >
            <RotateCcw/>
        </button>

        <button
                on:click={(e) => handleButtonClick('rotate-cw', e)}
                title="Rotate view 15° clockwise"
        >
            <RotateCw/>
        </button>

        <button
                on:click={(e) => handleButtonClick('right', e)}
                title="Rotate to next photo on the right"
        >
            <ArrowRightCircle/>
        </button>
    </div>
</div>

<style>
    .map {
        width: 100%;
        height: 100%;
        position: relative;
    }

    .control-buttons-container {
        position: absolute;
        bottom: 0;
        right: 0;
        z-index: 30000;
        pointer-events: none; /* This makes the container transparent to mouse events */
    }

    .buttons {
        display: flex;
        gap: 0.5rem;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 0.15rem;
        border-radius: 0.5rem 0 0 0;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        pointer-events: auto; /* This makes the buttons clickable */
    }

    .buttons button {
        cursor: pointer;
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        padding: 0.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: background-color 0.2s;
    }

    .buttons button:hover {
        background-color: #f0f0f0;
    }

    .buttons button:active {
        background-color: #e0e0e0;
    }

    .svg-overlay {
        position: absolute;
        top: 0;
        left: 0;
        z-index: 750;
    }

    .photo-direction-arrow svg {
        transition: transform 0.3s ease;
    }
</style>
