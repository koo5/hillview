<script lang="ts">
    import {onMount, onDestroy, tick} from 'svelte';
    import {Polygon, LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle, MapPin, Pause, ArrowUp, ArrowDown} from 'lucide-svelte';
    import L from 'leaflet';
    import 'leaflet/dist/leaflet.css';
    import Spinner from './Spinner.svelte';
    import { geolocation, type GeolocationPosition } from '$lib/geolocation';

    import {
        app,
        pos,
        update_pos,
        pos2,
        bearing,
        photos_in_area,
        photo_in_front,
        photo_to_left,
        photo_to_right,
        update_bearing,
        turn_to_photo_to, update_pos2
    } from "$lib/data.svelte";
    import {sources} from "$lib/sources";

    import {get} from "svelte/store";

    let flying = false;
    let programmaticMove = false; // Flag to prevent position sync conflicts
    let locationTrackingLoading = false;
    let locationApiEventFlashTimer: any = null;
    let locationApiEventFlash = false;
    let map: any;
    let elMap: any;
    const fov_circle_radius_px = 70;
    
    // Slideshow variables
    let slideshowActive = false;
    let slideshowDirection: 'left' | 'right' | null = null;
    let slideshowTimer: any = null;
    let slideshowInterval = 5000; // 5 seconds
    let longPressTimeout: any = null;
    const longPressDelay = 500; // 500ms for long press detection
    
    // Location tracking variables
    let locationTracking = false;
    let watchId: number | null = null;
    let userLocationMarker: any = null;
    let accuracyCircle: any = null;
    let userHeading: number | null = null;

    function createDirectionalArrow(photo: any) {
        let bearing = Math.round(photo.bearing);
        let color = photo.source.color;
        let frc = '';
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
            frc = photo.bearing_color;
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
        const arrowTipY_outer = outer_size * 0.12;
        const arrowBaseY_outer = inner_size * 0.82;
        const arrowWidth_outer = outer_size * 0.16;

        let svg = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" fill="none" xmlns="http://www.w3.org/2000/svg">`;

        if (photo === $photo_in_front) {
            svg += `<polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_outer}
                 ${half + arrowWidth_outer},${arrowBaseY_outer}
                 ${half - arrowWidth_outer},${arrowBaseY_outer}"
               stroke="${frc}" stroke-linecap="round" stroke-width="${stroke_width}"   />`
        //      <line x1="${half}" y1="${arrowTipY_outer * 4}" x2="${half}" y2="${arrowBaseY_outer}" stroke="${frc}" stroke-width="${stroke_width}" ${dashes} />
        }

        svg += `<polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_inner}
                 ${half + arrowWidth_inner},${arrowBaseY_inner}
                 ${half - arrowWidth_inner},${arrowBaseY_inner}"
                 ${fill} fill-opacity=0.8
               stroke="${color}" stroke-width="1" />`

        svg += '</svg>';

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

    pos.subscribe((v) => {
        if (!map || programmaticMove) return;
        if (map.getCenter() !== v.center || map.getZoom() !== v.zoom) {
            console.log('setView', v.center, v.zoom);
            map.setView(new LatLng(v.center.lat, v.center.lng), v.zoom);
            onMapStateChange(true, 'pos.subscribe');
        }
    });

    async function mapStateUserEvent(event: any) {

        if (!flying) {
            let _center = map.getCenter();
            let p = get(pos);
            console.log('mapStateUserEvent:', event);
            if (p.center.lat != _center.lat || p.center.lng != _center.lng) {
                console.log('p.center:', p.center, '_center:', _center);
                console.log('disableLocationTracking');
                disableLocationTracking();
            }
        }
        await onMapStateChange(true, 'mapStateUserEvent');
    }


    async function onMapStateChange(force: boolean, reason: string) {
        await tick();
        let _center = map.getCenter();
        let _zoom = map.getZoom();
        console.log('onMapStateChange force:', force, 'reason:', reason, 'center:', _center, '_zoom:', _zoom);
        let p = get(pos);
        let new_v = {
            ...p,
            center: new LatLng(_center.lat, _center.lng),
            zoom: _zoom,
            reason: `onMapStateChange(${force}, ${reason})`,
        };

        // Remove obsolete event check

        if (force === true || p.center.lat !== new_v.center.lat || p.center.lng !== new_v.center.lng || p.zoom !== new_v.zoom) {
            update_pos((value) => {
                return new_v;
            });
            update_pos2((value) => {
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
    async function handleButtonClick(action: string, event: Event) {
        event.preventDefault();
        event.stopPropagation();

        // Stop slideshow if it's active
        if (slideshowActive) {
            stopSlideshow();
        }

        if (action === 'left') {
            await turn_to_photo_to('left');
        } else if (action === 'right') {
            await turn_to_photo_to('right');
        } else if (action === 'rotate-ccw') {
            update_bearing(-15);
        } else if (action === 'rotate-cw') {
            update_bearing(15);
        } else if (action === 'forward') {
            moveForward();
        } else if (action === 'backward') {
            moveBackward();
        } else if (action === 'location') {
            toggleLocationTracking();
        }

        return false;
    }
    
    // Start slideshow in the specified direction
    function startSlideshow(direction: 'left' | 'right') {
        if (slideshowActive && slideshowDirection === direction) {
            // If already running in this direction, stop it
            stopSlideshow();
            return;
        }
        
        slideshowActive = true;
        slideshowDirection = direction;
        
        // Clear any existing timer
        if (slideshowTimer) {
            clearInterval(slideshowTimer);
        }
        
        // Immediately perform the first action
        performSlideshowAction();
        
        // Set up interval for subsequent actions
        slideshowTimer = setInterval(performSlideshowAction, slideshowInterval);
    }
    
    // Stop the slideshow
    function stopSlideshow() {
        slideshowActive = false;
        slideshowDirection = null;
        if (slideshowTimer) {
            clearInterval(slideshowTimer);
            slideshowTimer = null;
        }
    }
    
    // Perform the slideshow action based on current direction
    async function performSlideshowAction() {
        if (slideshowDirection === 'left' && $photo_to_left) {
            await turn_to_photo_to('left');
        } else if (slideshowDirection === 'right' && $photo_to_right) {
            await turn_to_photo_to('right');
        } else {
            // If no more photos in this direction, stop slideshow
            stopSlideshow();
        }
    }
    
    // Handle mouse down for long press detection
    function handleMouseDown(direction: 'left' | 'right', event: MouseEvent) {
        event.preventDefault();
        
        // Set timeout for long press
        longPressTimeout = setTimeout(() => {
            startSlideshow(direction);
        }, longPressDelay);
    }
    
    // Handle mouse up to cancel long press if released early
    function handleMouseUp(event: MouseEvent) {
        event.preventDefault();
        if (longPressTimeout) {
            clearTimeout(longPressTimeout);
            longPressTimeout = null;
        }
    }
    
    function disableLocationTracking() {
        if (locationTracking) {
            toggleLocationTracking();
        }
    }
    
    // Move in a direction relative to current bearing
    function move(direction: string) {
        // Ensure we have the latest map state
        if (!map) return;
        
        const currentBearing = get(bearing);
        const _center = map.getCenter();
        
        // Use the same approach as get_range function
        // First, convert center to container point
        const centerPoint = map.latLngToContainerPoint(_center);
        
        // Calculate pixel movement based on bearing
        const pixelDistance = fov_circle_radius_px;
        
        // Adjust bearing based on direction
        const adjustedBearing = direction === 'backward' ? (currentBearing + 180) % 360 : currentBearing;
        
        // Convert bearing to radians
        const bearingRad = (adjustedBearing * Math.PI) / 180;
        
        // Calculate pixel offset
        const dx = pixelDistance * Math.sin(bearingRad);
        const dy = -pixelDistance * Math.cos(bearingRad);
        
        // Create new point in container coordinates
        const newPoint = L.point(centerPoint.x + dx, centerPoint.y + dy);
        
        // Convert back to lat/lng
        const newCenter = map.containerPointToLatLng(newPoint);
        
        console.log(`move ${direction}:`, {
            bearing: currentBearing,
            adjustedBearing: adjustedBearing,
            centerPoint: centerPoint,
            dx: dx,
            dy: dy,
            newPoint: newPoint,
            oldCenter: _center,
            newCenter: newCenter
        });
        
        // Set flag to prevent position sync conflicts
        programmaticMove = true;
        
        // Fly to new position
        map.flyTo(newCenter, map.getZoom());
        
        // Update the position state
        update_pos((p) => ({
            ...p,
            center: newCenter,
            reason: direction
        }));
        
        // Reset flag after the movement is complete
        setTimeout(() => {
            programmaticMove = false;
        }, 1000); // Allow time for flyTo animation
    }
    
    // Convenience functions
    function moveForward() {
        move('forward');
    }
    
    function moveBackward() {
        move('backward');
    }

    function toggleLocationTracking() {
        if (locationTracking) {
            stopLocationTracking();
        } else {
            startLocationTracking();
        }
        locationTracking = !locationTracking;
    }
    
    // Start tracking user location
    async function startLocationTracking() {
        locationTrackingLoading = true;
        
        // Get initial position
        await geolocation.getCurrentPosition(
            updateUserLocation,
            (error) => {
                console.error("Error getting location:", error);
                alert(`Unable to get your location: ${error.message}`);
                locationTracking = false;
                locationTrackingLoading = false;
            },
            { enableHighAccuracy: true }
        );
        
        // Start watching position
        watchId = await geolocation.watchPosition(
            updateUserLocation,
            (error) => {
                console.error("Error watching location:", error);
            },
            { enableHighAccuracy: true }
        );
    }
    
    // Stop tracking user location
    async function stopLocationTracking() {
        locationTrackingLoading = false;
        if (watchId !== null) {
            await geolocation.clearWatch(watchId);
            watchId = null;
        }
    }
    
    // Update user location on the map
    async function updateUserLocation(position: GeolocationPosition) {
        const { latitude, longitude, accuracy, heading } = position.coords;

        console.log("updateUserLocation:", latitude, longitude, accuracy, heading);
        locationTrackingLoading = false;
        locationApiEventFlash = true;
        if (locationApiEventFlashTimer !== null) {
            clearTimeout(locationApiEventFlashTimer);
        }
        locationApiEventFlashTimer = setTimeout(() => {
            locationApiEventFlash = false;
        }, 100);
        
        // Update user heading if available
        if (heading !== null && heading !== undefined) {
            userHeading = heading;
            // Optionally update the app bearing based on user heading
            if (locationTracking) {
                update_bearing(userHeading);
            }
        }
        
        if (map) {
            const latLng = new L.LatLng(latitude, longitude);

            // Center map on user location if tracking is active
            if (locationTracking) {
                flying = true;
                update_pos((value) => {
                    return {
                        ...value,
                        center: new LatLng(latitude, longitude),
                        reason: 'updateUserLocation'
                    };
                });
                await tick();
                map.flyTo(latLng);
                await tick();
                setTimeout(() => {
                    flying = false;
                }, 500);

                // Update the app position
                update_pos((value) => {
                    return {
                        ...value,
                        center: new LatLng(latitude, longitude),
                        reason: 'updateUserLocation'
                    };
                });
                
                // Update other state as needed
                //onMapStateChange(true, 'updateUserLocation');
            }
        }
    }

    $: map = elMap?.getMap();

    onMount(async () => {
        await console.log('Map component mounted');
        await onMapStateChange(true, 'mount');
        await console.log('Map component mounted - after onMapStateChange');
    });

    export function setView(center: any, zoom: number) {
        if (map) {
            map.setView(center, zoom);
        }
    }

    //import.meta.hot?.dispose(() => (map = null));

    onDestroy(async () => {
        console.log('Map component destroyed');
        // Clean up geolocation watcher if active
        if (watchId !== null) {
            await geolocation.clearWatch(watchId);
        }
        
        // Clean up slideshow timer if active
        if (slideshowTimer) {
            clearInterval(slideshowTimer);
        }
        
        // Clean up long press timeout if active
        if (longPressTimeout) {
            clearTimeout(longPressTimeout);
        }
    });

    function toggleSourceVisibility(sourceId: string) {
        sources.update(sources => {
            const source = sources.find(s => s.id === sourceId);
            if (source) {
                source.enabled = !source.enabled;
            }
            return sources;
        });
    }

    let width: number;
    let height: number;

    // For the bearing overlay arrow:
    let centerX: number;
    $: centerX = width / 2;
    let centerY: number;
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
            bind:this={elMap}
            events={{moveend: mapStateUserEvent, zoomend: mapStateUserEvent}}
            options={{center: [$pos.center.lat, $pos.center.lng], zoom: $pos.zoom}}
    >

        <ScaleControl options={{maxWidth: 100}} position="bottomleft"/>

        <!-- Base map tiles -->
        <TileLayer
                {...{ attribution: "&copy; OpenStreetMap contributors" }}
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
                    {...{ title: `Photo at ${photo.coord.lat.toFixed(6)}, ${photo.coord.lng.toFixed(6)}\nDirection: ${photo.bearing.toFixed(1)}°\n(Relative: ${(photo.bearing - $bearing).toFixed(1)}°)` }}
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
                on:click={async (e) => {await handleButtonClick('left', e)}}
                on:mousedown={(e) => handleMouseDown('left', e)}
                on:mouseup={handleMouseUp}
                on:mouseleave={handleMouseUp}
                title={slideshowActive && slideshowDirection === 'left' ? 
                      "Stop slideshow" : 
                      "Rotate to next photo on the left (long press for slideshow)"}
                disabled={!$photo_to_left}
                class:slideshow-active={slideshowActive && slideshowDirection === 'left'}
        >
            {#if slideshowActive && slideshowDirection === 'left'}
                <Pause />
            {:else}
                <ArrowLeftCircle/>
            {/if}
        </button>

        <button
                on:click={async (e) => {await handleButtonClick('rotate-ccw', e)}}
                title="Rotate view 15° counterclockwise"
        >
            <RotateCcw/>
        </button>

        <button
                on:click={(e) => handleButtonClick('forward', e)}
                title="Move forward in viewing direction"
        >
            <ArrowUp/>
        </button>

        <button
                on:click={(e) => handleButtonClick('backward', e)}
                title="Move backward"
        >
            <ArrowDown/>
        </button>

        <button
                on:click={(e) => handleButtonClick('rotate-cw', e)}
                title="Rotate view 15° clockwise"
        >
            <RotateCw/>
        </button>

        <button
                on:click={(e) => handleButtonClick('right', e)}
                on:mousedown={(e) => handleMouseDown('right', e)}
                on:mouseup={handleMouseUp}
                on:mouseleave={handleMouseUp}
                title={slideshowActive && slideshowDirection === 'right' ? 
                      "Stop slideshow" : 
                      "Rotate to next photo on the right (long press for slideshow)"}
                disabled={!$photo_to_right}
                class:slideshow-active={slideshowActive && slideshowDirection === 'right'}
        >
            {#if slideshowActive && slideshowDirection === 'right'}
                <Pause />
            {:else}
                <ArrowRightCircle/>
            {/if}
        </button>
    </div>
</div>

<!-- Location tracking button -->
<div class="location-button-container">
    <button 
        class={locationTracking ? 'active' : ''}
        on:click={(e) => handleButtonClick('location', e)}
        title="Track my location"
        class:flash={locationApiEventFlash}
    >
        <MapPin />
        {#if locationTrackingLoading}
            <Spinner show={true} color="#4285F4"></Spinner>
        {/if}
    </button>
</div>

<div class="source-buttons-container">
    {#each $sources as source}
        <button
                class={source.enabled ? 'active' : ''}
                on:click={() => toggleSourceVisibility(source.id)}
                title={`Toggle ${source.name} visibility`}
        >
            <div class="source-icon" style="background-color: {source.color}"></div>
            {source.name}
            <Spinner show={source.enabled && !!source.requests.length} color="#4285F4"></Spinner>
        </button>
    {/each}
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
    
    .buttons button.slideshow-active {
        background-color: #4285F4;
        color: white;
        border-color: #3367d6;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% {
            box-shadow: 0 0 0 0 rgba(66, 133, 244, 0.7);
        }
        70% {
            box-shadow: 0 0 0 10px rgba(66, 133, 244, 0);
        }
        100% {
            box-shadow: 0 0 0 0 rgba(66, 133, 244, 0);
        }
    }
    
    .location-button-container {
        position: absolute;
        top: 0px;
        right: 10px;
        z-index: 30000;
    }
    
    .location-button-container button {
        cursor: pointer;
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        padding: 0.5rem;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .location-button-container button:hover {
        background-color: #f0f0f0;
    }
    
    .location-button-container button.active {
        background-color: #4285F4;
        color: white;
        border-color: #3367d6;
    }

    .location-button-container button.flash {
        border-radius: 100%;
    }


    .source-buttons-container {
        position: absolute;
        top: 50px;
        right: 10px;
        z-index: 30000;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin: 0;
        padding: 0;
    }

    .source-buttons-container button {
        cursor: pointer;
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        padding: 0.4rem;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .source-buttons-container button:hover {
        background-color: #f0f0f0;
    }

    .source-buttons-container button.active {
        background-color: #4285F4;
        color: white;
        border-color: #3367d6;
    }

    .svg-overlay {
        position: absolute;
        top: 0;
        left: 0;
        z-index: 750;
    }

    .source-icon {
        width: 1rem;
        height: 1rem;
        border-radius: 5%;
        margin-right: 0.5rem;
        border: 1px solid #ccc;
    }


</style>
