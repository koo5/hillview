<script lang="ts">
    import {onMount, onDestroy, tick} from 'svelte';
    import {Polygon, LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle, MapPin, Pause, ArrowUp, ArrowDown, Layers, Eye, Compass} from 'lucide-svelte';
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
    import { updateGpsLocation, setLocationTracking, setLocationError, gpsLocation } from "$lib/location.svelte";
    import { compassActive, compassAvailable, startCompass, stopCompass } from "$lib/compass.svelte";

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
    
    // Compass tracking variables
    let compassTrackingEnabled = false;
    
    // Subscribe to compass tracking state
    $: compassTrackingEnabled = $compassActive;
    
    // Debug bounds rectangle
    let boundsRectangle: any = null;
    let userHeading: number | null = null;
    let userLocation: GeolocationPosition | null = null;
    
    // Source buttons display mode
    let compactSourceButtons = true;
    
    // Export location tracking functions for use by parent
    export function enableLocationTracking() {
        if (!locationTracking) {
            locationTracking = true;
            setLocationTracking(true);
            startLocationTracking();
        }
    }
    
    export function disableLocationTracking() {
        if (locationTracking) {
            locationTracking = false;
            setLocationTracking(false);
            stopLocationTracking();
        }
    }
    
    export function getLocationData() {
        return userLocation;
    }

    function createDirectionalArrow(photo: any) {
        const zoomLevel = $pos.zoom;
        const isZoomedOut = zoomLevel < 10;
        
        // Completely separate implementation for zoomed out
        if (isZoomedOut) {
            return createSimpleTriangle(photo);
        }
        
        // Original implementation for zoomed in
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

        //console.log('createDirectionalArrow:', photo.id, $photo_in_front?.id, '$photo_in_front === photo', $photo_in_front?.id === photo.id);

        if ($photo_in_front?.id === photo.id) {
            //dashes = 'stroke-dasharray="20 4"'
            dashes = 'stroke-dasharray="1 10"'
            frc = photo.bearing_color || color;
            fill = `fill="${color}"`;
            stroke_width = 2
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

        // inner arrow with bearing color fill
        svg += `<polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_outer}
                 ${half + arrowWidth_outer},${arrowBaseY_outer}
                 ${half - arrowWidth_outer},${arrowBaseY_outer}"
               fill="${photo.bearing_color || '#9E9E9E'}" 
               fill-opacity="0.6"
               stroke="${photo === $photo_in_front ? frc : 'none'}" 
               stroke-width="${photo === $photo_in_front ? stroke_width : 0}" />`

        // outer arrow with source color stroke only
        svg += `<polygon transform="rotate(${bearing} ${half} ${half})"
               points="
                 ${half},${arrowTipY_inner}
                 ${half + arrowWidth_inner},${arrowBaseY_inner}
                 ${half - arrowWidth_inner},${arrowBaseY_inner}"
                 fill="none"
               stroke="${color}" stroke-width="${stroke_width}" />`

        svg += '</svg>';

        return L.divIcon({
            className: 'photo-direction-arrow',
            html: svg,
            iconSize: [size, size],
            iconAnchor: [half, half]
        });
    }
    
    function createSimpleTriangle(photo: any) {
        const size = 16; // Small fixed size
        const center = size / 2;
        const color = photo.source.color;
        const bearing = Math.round(photo.bearing);
        const isSelected = photo === $photo_in_front;
        
        // Simple triangle pointing up (will be rotated by bearing)
        const svg = `
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
                <g transform="rotate(${bearing} ${center} ${center})">
                    <path d="M ${center} 2 L ${size-2} ${size-2} L 2 ${size-2} Z" 
                          fill="${color}" 
                          fill-opacity="${isSelected ? 1 : 0.7}"
                          stroke="${photo.bearing_color || color}"
                          stroke-width="1"/>
                </g>
            </svg>
        `;
        
        return L.divIcon({
            className: 'photo-simple-triangle',
            html: svg,
            iconSize: [size, size],
            iconAnchor: [center, center] // Exactly centered
        });
    }

    // Calculate how many km are "visible" based on the current zoom/center
    function get_range(_center: LatLng) {
        if (!map) {
            console.warn('get_range called before map is ready');
            return 1000; // Default 1km
        }
        try {
            const pointC = map.latLngToContainerPoint(_center);
            // Move 100px to the right
            const pointR = L.point(pointC.x + fov_circle_radius_px, pointC.y);
            const latLngR = map.containerPointToLatLng(pointR);
            // distanceTo returns meters
            return _center.distanceTo(latLngR);
        } catch (e) {
            console.warn('Error calculating range:', e);
            return 1000; // Default 1km
        }
    }

    pos.subscribe((v) => {
        if (!map || programmaticMove) return;
        try {
            const currentCenter = map.getCenter();
            const currentZoom = map.getZoom();
            if (!currentCenter || currentCenter.lat !== v.center.lat || currentCenter.lng !== v.center.lng || currentZoom !== v.zoom) {
                console.log('setView', v.center, v.zoom);
                map.setView(new LatLng(v.center.lat, v.center.lng), v.zoom);
                onMapStateChange(true, 'pos.subscribe');
            }
        } catch (e) {
            // Map not ready yet, ignore
            console.log('Map not ready for pos update:', e);
        }
    });

    let moveEventCount = 0;
    let lastPruneTime = Date.now();
    
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
        
        // Prune tiles after significant movement or every 10 move events
        moveEventCount++;
        const timeSinceLastPrune = Date.now() - lastPruneTime;
        if (moveEventCount >= 10 || timeSinceLastPrune > 10000) {
            pruneTiles();
            moveEventCount = 0;
            lastPruneTime = Date.now();
        }
    }


    async function onMapStateChange(force: boolean, reason: string) {
        await tick();
        if (!map) {
            console.warn('onMapStateChange called before map is ready');
            return;
        }
        try {
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
                const bounds = map.getBounds();
                const newBounds = {
                    ...value,
                    range: get_range(_center),
                    top_left: bounds.getNorthWest(),
                    bottom_right: bounds.getSouthEast()
                };
                console.log('Map bounds updated:', {
                    nw: `${bounds.getNorthWest().lat}, ${bounds.getNorthWest().lng}`,
                    se: `${bounds.getSouthEast().lat}, ${bounds.getSouthEast().lng}`,
                    ne: `${bounds.getNorthEast().lat}, ${bounds.getNorthEast().lng}`,
                    sw: `${bounds.getSouthWest().lat}, ${bounds.getSouthWest().lng}`,
                    center: `${_center.lat}, ${_center.lng}`,
                    zoom: _zoom
                });
                return newBounds;
            });
        }
        } catch (e) {
            console.error('Error in onMapStateChange:', e);
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
        } else if (action === 'compass') {
            toggleCompassTracking();
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
        setLocationTracking(locationTracking);
    }
    
    async function toggleCompassTracking() {
        compassTrackingEnabled = !compassTrackingEnabled;
        
        if (compassTrackingEnabled) {
            console.log('🧭 Starting compass tracking...');
            const success = await startCompass();
            if (!success) {
                console.error('Failed to start compass');
                compassTrackingEnabled = false;
            }
        } else {
            console.log('🧭 Stopping compass tracking...');
            stopCompass();
        }
    }
    
    // Start tracking user location
    async function startLocationTracking() {
        locationTrackingLoading = true;
        
        // Get initial position
        await geolocation.getCurrentPosition(
            updateUserLocation,
            (error) => {
                console.error("Error getting location:", error);
                console.error("Error code:", error.code);
                console.error("Error message:", error.message);
                console.error("Full error object:", JSON.stringify(error));
                setLocationError(error.message);
                
                let errorMessage = "Unable to get your location: ";
                switch(error.code) {
                    case 1:
                        errorMessage += "Permission denied. Please allow location access.";
                        break;
                    case 2:
                        errorMessage += "Position unavailable. Please check if location services are enabled.";
                        break;
                    case 3:
                        errorMessage += "Request timed out.";
                        break;
                    default:
                        errorMessage += error.message;
                }
                
                alert(errorMessage);
                locationTracking = false;
                setLocationTracking(false);
                locationTrackingLoading = false;
            },
            { enableHighAccuracy: true }
        );
        
        // Start watching position
        watchId = await geolocation.watchPosition(
            updateUserLocation,
            (error) => {
                console.error("Error watching location:", error);
                console.error("Watch error code:", error.code);
                console.error("Watch error message:", error.message);
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
        // Clear the location data when stopping
        updateGpsLocation(null);
        setLocationError(null);
    }
    
    // Update user location on the map
    async function updateUserLocation(position: GeolocationPosition) {
        // Check if position changed and update global store
        const updated = updateGpsLocation(position);
        if (!updated) {
            //console.log("updateUserLocation(GPS): No change in position, skipping update");
            return;
        }

        const { latitude, longitude, accuracy, heading } = position.coords;
        
        // Store the location data locally
        userLocation = position;

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
    
    // Add tile pruning function for memory management
    function pruneTiles() {
        if (map && map.eachLayer) {
            map.eachLayer((layer: any) => {
                if (layer._tiles && layer._pruneTiles) {
                    layer._pruneTiles();
                }
            });
        }
    }
    
    // Periodically prune tiles to free memory
    let tilePruneInterval: any = null;
    $: if (map && !tilePruneInterval) {
        // Prune tiles every 30 seconds
        tilePruneInterval = setInterval(pruneTiles, 30000);
    }
    
    // Fix Android mouse wheel behavior when map is ready
    $: if (map && /Android/i.test(navigator.userAgent)) {
        const mapContainer = map.getContainer();
        
        // Remove any existing wheel listeners first
        mapContainer.removeEventListener('wheel', handleAndroidWheel, true);
        mapContainer.removeEventListener('wheel', handleAndroidWheel, false);
        mapContainer.removeEventListener('mousewheel', handleAndroidWheel, true);
        mapContainer.removeEventListener('DOMMouseScroll', handleAndroidWheel, true);
        
        // Add our custom wheel handler with capture to intercept early
        mapContainer.addEventListener('wheel', handleAndroidWheel, { 
            passive: false, 
            capture: true 
        });
        mapContainer.addEventListener('mousewheel', handleAndroidWheel, { 
            passive: false, 
            capture: true 
        });
        mapContainer.addEventListener('DOMMouseScroll', handleAndroidWheel, { 
            passive: false, 
            capture: true 
        });
        
        // Also prevent default on the parent div
        const mapDiv = mapContainer.parentElement;
        if (mapDiv) {
            mapDiv.addEventListener('wheel', (e: Event) => e.preventDefault(), { passive: false });
        }
        
        // Disable Leaflet's built-in scroll wheel zoom since we're handling it manually
        map.scrollWheelZoom.disable();
    }
    
    let wheelTimeout: any = null;
    
    function handleAndroidWheel(e: WheelEvent) {
        console.log('Android wheel event:', { deltaY: e.deltaY, wheelDelta: (e as any).wheelDelta, detail: e.detail });
        
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        
        // Temporarily disable dragging to prevent pan
        if (map && map.dragging.enabled()) {
            map.dragging.disable();
            
            // Clear any existing timeout
            if (wheelTimeout) {
                clearTimeout(wheelTimeout);
            }
            
            // Re-enable dragging after a short delay
            wheelTimeout = setTimeout(() => {
                if (map) {
                    map.dragging.enable();
                }
                wheelTimeout = null;
            }, 100);
        }
        
        const delta = e.deltaY || (e as any).wheelDelta || -e.detail;
        if (delta && map) {
            const zoom = map.getZoom();
            const zoomDelta = delta > 0 ? -0.5 : 0.5;
            const newZoom = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), zoom + zoomDelta));
            
            console.log('Zooming from', zoom, 'to', newZoom);
            
            // Get the mouse position relative to the map
            const containerPoint = map.mouseEventToContainerPoint(e);
            
            // Zoom to the mouse position
            map.setZoomAround(containerPoint, newZoom, { animate: false });
        }
        
        return false;
    }

    onMount(async () => {
        await console.log('Map component mounted');
        await onMapStateChange(true, 'mount');
        await console.log('Map component mounted - after onMapStateChange');
        
        // Compass availability is automatically tracked by the store
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
        
        // Clean up wheel timeout if active
        if (wheelTimeout) {
            clearTimeout(wheelTimeout);
        }
        
        // Clean up tile pruning interval
        if (tilePruneInterval) {
            clearInterval(tilePruneInterval);
            tilePruneInterval = null;
        }
        
        // Clean up Android wheel event listener
        if (map && /Android/i.test(navigator.userAgent)) {
            const mapContainer = map.getContainer();
            mapContainer.removeEventListener('wheel', handleAndroidWheel, true);
            mapContainer.removeEventListener('wheel', handleAndroidWheel, false);
            
            const mapDiv = mapContainer.parentElement;
            if (mapDiv) {
                mapDiv.removeEventListener('wheel', (e: Event) => e.preventDefault());
            }
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
    
    // Create a reactive key that changes whenever photos change
    let photosUpdateKey = 0;
    $: if ($photos_in_area) {
        photosUpdateKey = Date.now();
    }

</script>


<!-- The map container -->
<div bind:clientHeight={height} bind:clientWidth={width} class="map">
    <LeafletMap
            bind:this={elMap}
            events={{moveend: mapStateUserEvent, zoomend: mapStateUserEvent}}
            options={{
                center: [$pos.center.lat, $pos.center.lng], 
                zoom: $pos.zoom,
                minZoom: 3,
                maxZoom: 23,
                zoomControl: true, 
                scrollWheelZoom: !/Android/i.test(navigator.userAgent), // Disable on Android, we'll handle it manually
                touchZoom: true,
                dragging: true,
                bounceAtZoomLimits: true,
                // Memory optimization settings
                preferCanvas: true, // Use Canvas renderer for better performance
                maxBoundsViscosity: 1.0 // Prevent excessive panning
            }}
    >

        <ScaleControl options={{maxWidth: 100, imperial: false}} position="bottomleft"/>

        <!-- Base map tiles -->
        <TileLayer
                {...{ attribution: "&copy; OpenStreetMap contributors" }}
                options={{
                    maxZoom: 23,
                    maxNativeZoom: 19,
                    minZoom: 3,
                    // Memory optimization for tiles
                    keepBuffer: 1, // Keep fewer tiles in memory (default is 2)
                    updateWhenIdle: true, // Update tiles only when panning ends
                    updateWhenZooming: false, // Don't update during zoom animation
                    tileSize: 256, // Standard tile size
                    zoomOffset: 0,
                    detectRetina: false, // Disable retina tiles to save memory
                    crossOrigin: true, // Enable CORS for better caching
                    // Additional performance options
                    updateInterval: 200, // Throttle tile updates
                    tms: false,
                    noWrap: false,
                    zoomReverse: false,
                    opacity: 1,
                    zIndex: 1,
                    bounds: undefined, // No bounds restriction
                    className: 'map-tiles'
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

        <!-- Debug bounds rectangle -->
        {#if $app.debug > 0 && $pos2.top_left && $pos2.bottom_right}
            <Polygon
                    latLngs={[
                        [$pos2.top_left.lat, $pos2.top_left.lng],
                        [$pos2.top_left.lat, $pos2.bottom_right.lng],
                        [$pos2.bottom_right.lat, $pos2.bottom_right.lng],
                        [$pos2.bottom_right.lat, $pos2.top_left.lng]
                    ]}
                    color="#FF0000"
                    fillColor="#FF0000"
                    fillOpacity={0.1}
                    weight={2}
                    dashArray="5, 10"
                />
        {/if}

        <!-- Markers for photos -->
        {#key photosUpdateKey}
            {#each $photos_in_area as photo (photo.id)}
                <Marker
                        zIndexOffset={10000*180-photo.abs_bearing_diff*10000}
                        latLng={photo.coord}
                        icon={createDirectionalArrow(photo)}
                        {...{ title: `Photo at ${photo.coord.lat.toFixed(6)}, ${photo.coord.lng.toFixed(6)}\nDirection: ${photo.bearing.toFixed(1)}°\n(Relative: ${(photo.bearing - $bearing).toFixed(1)}°)` }}
                />
            {/each}
        {/key}

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

<!-- Debug bounds info -->
{#if $app.debug > 0 && $pos2.top_left && $pos2.bottom_right}
    <div class="debug-bounds-info">
        <div>Bounds:</div>
        <div>NW: {$pos2.top_left.lat.toFixed(6)}, {$pos2.top_left.lng.toFixed(6)}</div>
        <div>SE: {$pos2.bottom_right.lat.toFixed(6)}, {$pos2.bottom_right.lng.toFixed(6)}</div>
        <div>Width: {($pos2.bottom_right.lng - $pos2.top_left.lng).toFixed(6)}°</div>
        <div>Height: {($pos2.top_left.lat - $pos2.bottom_right.lat).toFixed(6)}°</div>
    </div>
{/if}

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

<!-- Location tracking buttons -->
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
    <button 
        class={compassTrackingEnabled ? 'active' : ''}
        on:click={(e) => handleButtonClick('compass', e)}
        title="Track compass bearing"
        disabled={!$compassAvailable}
    >
        <Compass />
    </button>
</div>

<div class="source-buttons-container" class:compact={compactSourceButtons}>
    <button
        class="toggle-compact {compactSourceButtons ? 'active' : ''}"
        on:click={() => compactSourceButtons = !compactSourceButtons}
        title={compactSourceButtons ? "Show labels" : "Hide labels"}
    >
        <Layers size={16} />
    </button>
    {#each $sources as source}
        <button
                class={source.enabled ? 'active' : ''}
                on:click={() => toggleSourceVisibility(source.id)}
                title={`Toggle ${source.name} visibility`}
        >
            <div class="source-icon-wrapper">
                <Spinner show={source.enabled && !!source.requests.length} color="#fff"></Spinner>
                <div class="source-icon" style="background-color: {source.color}"></div>
            </div>
            {#if !compactSourceButtons}
                {source.name}
            {/if}
        </button>
    {/each}
</div>

<style>


    .map {
        width: 100%;
        height: 100%;
        position: relative;
    }

    .debug-bounds-info {
        position: absolute;
        top: 10px;
        left: 10px;
        background-color: rgba(255, 255, 255, 0.9);
        padding: 10px;
        border-radius: 5px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        z-index: 30000;
        font-family: monospace;
        font-size: 12px;
        line-height: 1.4;
    }

    .debug-bounds-info div {
        margin: 2px 0;
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
        background-color: rgba(255, 255, 255, 0.1);
        padding: 0.15rem;
        border-radius: 0.5rem 0 0 0;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        pointer-events: auto; /* This makes the buttons clickable */
    }

    .buttons button {
        cursor: pointer;
        background-color: rgba(255, 255, 255, 0.5) !important;
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
        display: flex;
        gap: 8px;
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
    
    .location-button-container button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .location-button-container button:disabled:hover {
        background-color: white;
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

    .source-icon-wrapper {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        margin-right: 0.5rem;
    }
    
    .source-icon {
        width: 1rem;
        height: 1rem;
        border-radius: 5%;
        border: 1px solid #ccc;
    }
    
    .source-icon-wrapper :global(.spinner-container) {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
    }
    
    /* Compact mode styles */
    .source-buttons-container.compact button {
        padding: 0.5rem;
        width: 40px;
        height: 40px;
        justify-content: center;
    }
    
    .source-buttons-container.compact .source-icon-wrapper {
        margin-right: 0;
    }
    
    /* Toggle button styles */
    .toggle-compact {
        border: 1px solid #999 !important;
        background-color: #f8f8f8 !important;
        transition: all 0.2s;
    }
    
    .toggle-compact:hover {
        background-color: #e8e8e8 !important;
    }
    
    .toggle-compact.active {
        background-color: #666 !important;
        color: white !important;
        border-color: #555 !important;
    }

    /* Ensure zoom controls have higher z-index than scale control */
    :global(.leaflet-control-zoom-in) {
        background-color: rgba(255, 255, 255, 0.5) !important;
    }

    /* Ensure zoom controls have higher z-index than scale control */
    :global(.leaflet-control-zoom-out) {
        background-color: rgba(255, 255, 255, 0.5) !important;
    }

</style>
