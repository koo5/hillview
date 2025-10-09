<script lang="ts">
    import {onMount, onDestroy, tick} from 'svelte';
    import {LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle, MapPin, Pause, ArrowUp, ArrowDown, Layers, Eye, Compass, Car, PersonStanding, Map as MapIcon} from 'lucide-svelte';
    import L from 'leaflet';
    import 'leaflet/dist/leaflet.css';
    import { getCurrentProviderConfig, setTileProvider, currentTileProvider } from '$lib/tileProviders';
    import Spinner from './Spinner.svelte';
    import TileProviderSelector from './TileProviderSelector.svelte';
    import { getCurrentPosition, type GeolocationPosition } from '$lib/preciseLocation';
    import { locationManager } from '$lib/locationManager';

    import {
        spatialState,
        bearingState,
        visiblePhotos,
        photoToLeft,
        photoToRight,
        updateSpatialState,
        updateBearing,
        updateBearingByDiff,
        type BearingMode,
        bearingMode
    } from "$lib/mapState";
    import { placeholderPhotos } from '$lib/placeholderInjector';
    import { sources } from "$lib/data.svelte";
    import { simplePhotoWorker } from '$lib/simplePhotoWorker';
    import { turn_to_photo_to, app, mapillary_cache_status, sourceLoadingStatus } from "$lib/data.svelte";
    import { updateGpsLocation, setLocationTracking, setLocationError, gpsLocation, locationTracking } from "$lib/location.svelte";
    import { compassActive, compassAvailable, startCompass, stopCompass, currentCompassHeading } from "$lib/compass.svelte";
    import { optimizedMarkerSystem } from '$lib/optimizedMarkers';
    import '$lib/styles/optimizedMarkers.css';

    import {get} from "svelte/store";
	import {stringifyCircularJSON} from "$lib/utils/json";

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

    // Location tracking variables (now managed by preciseLocation module)
    let userLocationMarker: any = null;
    let accuracyCircle: any = null;
    let wasTrackingBeforeHidden = false;
    let orientationRestartTimer: any = null;

    // Compass tracking variables
    let compassTrackingEnabled = false;

    // Optimized marker system variables
    let currentMarkers: L.Marker[] = [];
    let lastPhotosUpdate = 0;

    // Location tracking re-enable timer
    let locationReEnableTimer: number | null = null;

    // Flag to track if the current map event was caused by zoom buttons
    let isZoomButtonEvent = false;
    let zoomButtonEventTimer: number | null = null;

    // Subscribe to compass tracking state
    $: compassTrackingEnabled = $compassActive;

    // Debug bounds rectangle
    let boundsRectangle: any = null;
    let userHeading: number | null = null;
    let userLocation: GeolocationPosition | null = null;

    // Source buttons display mode
    let compactSourceButtons = true;


    $: map = elMap?.getMap();

    // Expose map to window for testing
    $: if (map && typeof window !== 'undefined') {
        (window as any).leafletMap = map;
    }



    // Export location tracking functions for use by parent
    export function enableLocationTracking() {
        if (!get(locationTracking)) {
            setLocationTracking(true);
            startLocationTracking();
        }
    }

    export function disableLocationTracking() {
        if (get(locationTracking)) {
            setLocationTracking(false);
            stopLocationTracking();
        }
    }

    export function getLocationData() {
        return userLocation;
    }

    // Handle zoom button clicks to re-enable location tracking
    function handleZoomButtonClick() {
        console.log('🢄[LOCATION] Zoom button clicked');

        // Set flag to prevent location tracking from being disabled
        isZoomButtonEvent = true;

        // Clear any existing zoom button event timer
        if (zoomButtonEventTimer) {
            clearTimeout(zoomButtonEventTimer);
        }

        // Reset the flag after 500ms to handle multiple map events
        zoomButtonEventTimer = window.setTimeout(() => {
            console.log('🢄[LOCATION] Resetting zoom button event flag');
            isZoomButtonEvent = false;
            zoomButtonEventTimer = null;
        }, 500);

        if (get(locationTracking)) {
            console.log('🢄[LOCATION] Zoom button clicked while tracking - will re-enable after 200ms');

            // Clear any existing timer
            if (locationReEnableTimer) {
                clearTimeout(locationReEnableTimer);
            }

            // Re-enable location tracking after 200ms
            locationReEnableTimer = window.setTimeout(() => {
                if (get(locationTracking)) {
                    console.log('🢄[LOCATION] Re-enabling location tracking after zoom');
                    enableLocationTracking();
                }
            }, 200);
        }
    }

    // Set up event listeners for Leaflet zoom controls
    function setupZoomControlListeners() {
        if (!map) return;

        // Wait a bit for the zoom controls to be added to the DOM
        setTimeout(() => {
            const zoomInButton = document.querySelector('.leaflet-control-zoom-in');
            const zoomOutButton = document.querySelector('.leaflet-control-zoom-out');

            if (zoomInButton) {
                zoomInButton.addEventListener('click', handleZoomButtonClick);
                //console.log('🢄[LOCATION] Added zoom-in button listener');
            }

            if (zoomOutButton) {
                zoomOutButton.addEventListener('click', handleZoomButtonClick);
                //console.log('🢄[LOCATION] Added zoom-out button listener');
            }
        }, 100);
    }

    // Optimized marker management functions
    function updateOptimizedMarkers(photos: any[]) {
        if (!map) return;

        const updateId = Date.now();
        lastPhotosUpdate = updateId;

        console.log(`🢄Map: updateOptimizedMarkers called with ${photos.length} photos, updateId: ${updateId}`);

        // Use the optimized marker system
        const updatedMarkers = optimizedMarkerSystem.updateMarkers(map, photos);
        if (updatedMarkers) {
            currentMarkers = updatedMarkers;
            console.log(`🢄Map: Updated ${currentMarkers.length} optimized markers`);
        } else {
            console.warn('🢄Map: optimizedMarkerSystem.updateMarkers returned undefined');
        }
    }

    // Calculate how many km are "visible" based on the current zoom/center
    function get_range(_center: LatLng) {
        if (!map) {
            //console.warn('🢄get_range called before map is ready');
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
            console.warn('🢄Error calculating range:', e);
            return 1000; // Default 1km
        }
    }

    spatialState.subscribe((spatial) => {
        if (!map || programmaticMove) return;
        try {
            // Check if map is fully initialized with container
            if (!map.getContainer() || !map._loaded) return;

            const currentCenter = map.getCenter();
            const currentZoom = map.getZoom();
            if (!currentCenter || currentCenter.lat !== spatial.center.lat || currentCenter.lng !== spatial.center.lng || currentZoom !== spatial.zoom) {
                console.log('🢄setView', spatial.center, spatial.zoom);
                map.setView(new LatLng(spatial.center.lat, spatial.center.lng), spatial.zoom);
                onMapStateChange(true, 'spatialState.subscribe');
            }
        } catch (e) {
            // Map not ready yet, ignore
            //console.log('🢄Map not ready for spatialState update:', e instanceof Error ? e.message : String(e));
        }
    });

    let moveEventCount = 0;
    let lastPruneTime = Date.now();

    async function mapStateUserEvent(event: any) {

        if (!flying) {
            let _center = map.getCenter();
            let p = get(spatialState);
            //console.log('🢄mapStateUserEvent:', stringifyCircularJSON(event));
            if (p.center.lat != _center.lat || p.center.lng != _center.lng) {
                console.log('🢄p.center:', p.center, '_center:', _center);

                // Only disable location tracking if this wasn't caused by zoom buttons
                if (!isZoomButtonEvent) {
                    console.log('🢄disableLocationTracking');
                    disableLocationTracking();
                } else {
                    console.log('🢄Zoom button event detected - not disabling location tracking');
                }
            }
        }

        await onMapStateChange(true, 'mapStateUserEvent');

        // Prune tiles after significant movement or every 10 move events
        /*moveEventCount++;
        const timeSinceLastPrune = Date.now() - lastPruneTime;
        if (moveEventCount >= 10 || timeSinceLastPrune > 10000) {
            pruneTiles();
            moveEventCount = 0;
            lastPruneTime = Date.now();
        }*/
    }


    async function onMapStateChange(force: boolean, reason: string) {
        await tick();
        if (!map) {
            console.warn('🢄onMapStateChange called before map is ready');
            return;
        }
        try {
            let _center = map.getCenter();
            let _zoom = map.getZoom();
            console.log('🢄onMapStateChange: force:', force, 'reason:', reason, 'center:', JSON.stringify(_center), 'zoom:', _zoom);

            const currentSpatial = get(spatialState);
            const bounds = map.getBounds();
            const range = get_range(_center);

            // Normalize coordinates to valid lat/lng ranges
            const normalizeLng = (lng: number) => ((lng % 360) + 540) % 360 - 180;
            const normalizeLat = (lat: number) => Math.max(-90, Math.min(90, lat));

            const topLeft = bounds.getNorthWest();
            const bottomRight = bounds.getSouthEast();

            const newSpatialState = {
                center: new LatLng(_center.lat, _center.lng),
                zoom: _zoom,
                bounds: {
                    top_left: new LatLng(
                        normalizeLat(topLeft.lat),
                        normalizeLng(topLeft.lng)
                    ),
                    bottom_right: new LatLng(
                        normalizeLat(bottomRight.lat),
                        normalizeLng(bottomRight.lng)
                    )
                },
                range: range
            };

            // Debug log to verify normalization
            //console.log(`Map: Normalized bounds - TL: [${newSpatialState.bounds.top_left.lat.toFixed(6)}, ${newSpatialState.bounds.top_left.lng.toFixed(6)}], BR: [${newSpatialState.bounds.bottom_right.lat.toFixed(6)}, ${newSpatialState.bounds.bottom_right.lng.toFixed(6)}]`);

            if (force === true ||
                currentSpatial.center.lat !== newSpatialState.center.lat ||
                currentSpatial.center.lng !== newSpatialState.center.lng ||
                currentSpatial.zoom !== newSpatialState.zoom) {

                updateSpatialState(newSpatialState);

                /*console.log('🢄Map bounds updated:', JSON.stringify({
                    nw: `${bounds.getNorthWest().lat}, ${bounds.getNorthWest().lng}`,
                    se: `${bounds.getSouthEast().lat}, ${bounds.getSouthEast().lng}`,
                    ne: `${bounds.getNorthEast().lat}, ${bounds.getNorthEast().lng}`,
                    sw: `${bounds.getSouthWest().lat}, ${bounds.getSouthWest().lng}`,
                    center: `${_center.lat}, ${_center.lng}`,
                    zoom: _zoom
                }, null, 2));*/
            }
        } catch (e) {
            console.error('🢄Error in onMapStateChange:', e);
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

        // Disable compass tracking when any turn button is clicked
        if (action === 'left' || action === 'right' || action === 'rotate-ccw' || action === 'rotate-cw') {
            if (compassTrackingEnabled) {
                console.log('🢄🧭 Disabling compass tracking due to manual turn');
                await stopCompass();
                compassTrackingEnabled = false;
            }
        }

        if (action === 'left') {
            await turn_to_photo_to('left');
        } else if (action === 'right') {
            await turn_to_photo_to('right');
        } else if (action === 'rotate-ccw') {
            updateBearingByDiff(-15);
        } else if (action === 'rotate-cw') {
            updateBearingByDiff(15);
        } else if (action === 'forward') {
            moveForward();
        } else if (action === 'backward') {
            moveBackward();
        } else if (action === 'location') {
            toggleLocationTracking();
        } else if (action === 'compass') {
            toggleCompassTracking();
        } else if (action === 'bearing-mode') {
            toggleBearingMode();
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
        if (slideshowDirection === 'left' && $photoToLeft) {
            await turn_to_photo_to('left');
        } else if (slideshowDirection === 'right' && $photoToRight) {
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

        const currentBearing = get(bearingState).bearing;
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

        // Update the spatial state
        updateSpatialState({
            center: newCenter,
            zoom: map.getZoom(),
            bounds: null, // Will be updated by onMapStateChange
        });

        // Reset flag after the movement is complete
        setTimeout(() => {
            programmaticMove = false;
        }, 1000); // Allow time for flyTo animation
    }

    // Convenience functions (exported for keyboard shortcuts)
    export function moveForward() {
        move('forward');
    }

    export function moveBackward() {
        move('backward');
    }

    function toggleLocationTracking() {
        if (get(locationTracking)) {
            stopLocationTracking();
            setLocationTracking(false);
        } else {
            startLocationTracking();
            setLocationTracking(true);
        }
    }

    async function toggleCompassTracking() {
        compassTrackingEnabled = !compassTrackingEnabled;

        if (compassTrackingEnabled) {
            console.log('🢄🧭 Starting compass tracking...');
            const success = await startCompass();
            if (!success) {
                console.error('🢄Failed to start compass');
                compassTrackingEnabled = false;
            }
        } else {
            //console.log('🢄🧭 Stopping compass tracking...');
            stopCompass().catch(err => console.error('🢄Error stopping compass:', err));
        }
    }

    function toggleBearingMode() {
        const currentMode = $bearingMode;
        const newMode: BearingMode = currentMode === 'car' ? 'walking' : 'car';
        console.log(`🚗🚶 Switching bearing mode: ${currentMode} → ${newMode}`);
        bearingMode.set(newMode);
    }

    // Start tracking user location
    async function startLocationTracking() {
        locationTrackingLoading = true;

        try {
            console.log("📍 Map.svelte Starting location tracking");
            await locationManager.requestLocation('user');

            locationTrackingLoading = false;
            console.log("📍 Location tracking started successfully");

        } catch (error: any) {
            console.error("📍 Error starting location tracking:", error);
            setLocationError(error?.message || "Unknown error");

            let errorMessage = "Unable to get your location: ";
            if (error?.name === 'GeolocationPositionError' || error?.code) {
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
                        errorMessage += error?.message || "Unknown error";
                }
            } else {
                errorMessage += error?.message || "Unknown error";
            }

            alert(errorMessage);
            setLocationTracking(false);
            locationTrackingLoading = false;
        }
    }

    // Stop tracking user location
    async function stopLocationTracking() {
        locationTrackingLoading = false;

        try {
            console.log("📍 Stopping location tracking");
            await locationManager.releaseLocation('user');
        } catch (error) {
            console.error("📍 Error stopping location tracking:", error);
        }

        // Clear the location data when stopping
        updateGpsLocation(null);
        setLocationError(null);
    }

    // Handle GPS location updates only (position/coordinates)
    async function handleGpsLocationUpdate(position: GeolocationPosition) {
        const { latitude, longitude, accuracy } = position.coords;

        // Store the location data locally
        userLocation = position;

        console.log("handleGpsLocationUpdate:", latitude, longitude, accuracy);
        locationTrackingLoading = false;
        locationApiEventFlash = true;
        if (locationApiEventFlashTimer !== null) {
            clearTimeout(locationApiEventFlashTimer);
        }
        locationApiEventFlashTimer = setTimeout(() => {
            locationApiEventFlash = false;
        }, 100);

        if (map) {
            const latLng = new L.LatLng(latitude, longitude);

            // Center map on user location if tracking is active
            if (get(locationTracking)) {
                flying = true;
                updateSpatialState({
                    center: new LatLng(latitude, longitude),
                    zoom: map.getZoom(),
                    bounds: null, // Will be updated by onMapStateChange
                    range: get_range(new LatLng(latitude, longitude))
                }, 'gps');
                await tick();
                map.flyTo(latLng);
                await tick();
                setTimeout(() => {
                    flying = false;
                }, 500);

                // Update the spatial state
                updateSpatialState({
                    center: new LatLng(latitude, longitude),
                    zoom: map.getZoom(),
                    bounds: null, // Will be updated by onMapStateChange
                    range: get_range(new LatLng(latitude, longitude))
                }, 'gps');
            }
        }
    }

    // Handle GPS bearing updates (only when compass button active + car mode)
    function handleGpsBearingUpdate(position: GeolocationPosition) {
        const { heading } = position.coords;

        // Only update bearing if compass tracking is enabled AND in car mode
        if (compassTrackingEnabled && $bearingMode === 'car' && heading !== null && heading !== undefined) {
            userHeading = heading;
            console.log("handleGpsBearingUpdate: GPS heading", heading);
            updateBearing(heading);
        }
    }


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
    let bearingUpdateTimeout: any = null;

    function handleAndroidWheel(e: WheelEvent) {
        console.log('🢄Android wheel event:', { deltaY: e.deltaY, wheelDelta: (e as any).wheelDelta, detail: e.detail });

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

            console.log('🢄Zooming from', zoom, 'to', newZoom);

            // Get the mouse position relative to the map
            const containerPoint = map.mouseEventToContainerPoint(e);

            // Zoom to the mouse position
            map.setZoomAround(containerPoint, newZoom, { animate: false });
        }

        return false;
    }

    // Handle visibility changes (orientation changes, app backgrounding)
    function handleVisibilityChange() {
        if (document.hidden) {
            // App is going to background or orientation change starting
            wasTrackingBeforeHidden = get(locationTracking);
            console.log('🢄App visibility changed to hidden, was tracking:', wasTrackingBeforeHidden);
        } else {
            // App is coming to foreground or orientation change completed
            console.log('🢄App visibility changed to visible, should resume tracking:', wasTrackingBeforeHidden);
            if (wasTrackingBeforeHidden) {
                // Clear any existing timer
                if (orientationRestartTimer) {
                    clearTimeout(orientationRestartTimer);
                }
                // Delay restart slightly to let WebView stabilize after orientation change
                orientationRestartTimer = setTimeout(async () => {
                    if (wasTrackingBeforeHidden && !get(locationTracking)) {
                        console.log('🢄📍 Restarting location tracking after visibility change');
                        setLocationTracking(true);
                        await startLocationTracking();
                    }
                }, 500);
            }
        }
    }

    // Handle page show/hide events (iOS Safari specific)
    function handlePageShow(event: PageTransitionEvent) {
        if (event.persisted && wasTrackingBeforeHidden && !get(locationTracking)) {
            console.log('🢄📍 Page shown from cache, resuming location tracking');
            setLocationTracking(true);
            startLocationTracking();
        }
    }

    function handlePageHide(event: PageTransitionEvent) {
        if (event.persisted) {
            wasTrackingBeforeHidden = get(locationTracking);
            console.log('🢄Page hiding to cache, was tracking:', wasTrackingBeforeHidden);
        }
    }

    onMount(() => {
        console.log('🢄Map component mounted');

        // Initialize the simplified photo worker (async)
        (async () => {
            try {
                await simplePhotoWorker.initialize();
                //console.log('🢄SimplePhotoWorker initialized successfully');
            } catch (error) {
                console.error('🢄Failed to initialize SimplePhotoWorker:', error);
            }

            await onMapStateChange(true, 'mount');
            //console.log('🢄Map component mounted - after onMapStateChange');

            // Add zoom control after scale control for proper ordering
            const zoomControl = new L.Control.Zoom({ position: 'topleft' });
            map.addControl(zoomControl);

            // Add attribution control at bottom-left
            const attributionControl = new L.Control.Attribution({ position: 'bottomleft' });
            map.addControl(attributionControl);

            // Set up zoom control listeners
            setupZoomControlListeners();

            // Firefox fix: Force map resize after initialization
            if (navigator.userAgent.toLowerCase().includes('firefox')) {
                setTimeout(() => {
                    if (map && map.invalidateSize) {
                        console.log('🢄Firefox detected - forcing map resize');
                        map.invalidateSize({ reset: true, animate: false });
                    }
                }, 100);

                // Also add a longer timeout as backup
                setTimeout(() => {
                    if (map && map.invalidateSize) {
                        map.invalidateSize({ reset: true, animate: false });
                    }
                }, 500);
            }
        })();

        // Add event listeners for visibility changes
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('pageshow', handlePageShow);
        window.addEventListener('pagehide', handlePageHide);

        // Also listen for orientation changes directly
        window.addEventListener('orientationchange', () => {
            console.log('🢄Orientation change detected');
            // The visibility change handler will take care of restarting
        });

        return gpsLocation.subscribe((position: GeolocationPosition | null) => {
            if (position) {
                handleGpsLocationUpdate(position);
            }
        });
    });

    export function setView(center: any, zoom: number) {
        if (map) {
            map.setView(center, zoom);
        }
    }

    //import.meta.hot?.dispose(() => (map = null));

    onDestroy(async () => {
        console.log('🢄Map component destroyed');
        // Clean up location tracking if active
        try {
            await locationManager.releaseLocation('user');
        } catch (error) {
            console.debug('🢄📍 Error stopping location updates on destroy:', error);
        }

        // Clear timers
        if (orientationRestartTimer) {
            clearTimeout(orientationRestartTimer);
        }

        // Clean up location re-enable timer
        if (locationReEnableTimer) {
            clearTimeout(locationReEnableTimer);
            locationReEnableTimer = null;
        }

        // Clean up zoom button event timer
        if (zoomButtonEventTimer) {
            clearTimeout(zoomButtonEventTimer);
            zoomButtonEventTimer = null;
        }

        // Clean up zoom control event listeners
        const zoomInButton = document.querySelector('.leaflet-control-zoom-in');
        const zoomOutButton = document.querySelector('.leaflet-control-zoom-out');

        if (zoomInButton) {
            zoomInButton.removeEventListener('click', handleZoomButtonClick);
        }
        if (zoomOutButton) {
            zoomOutButton.removeEventListener('click', handleZoomButtonClick);
        }

        // Remove event listeners
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        window.removeEventListener('pageshow', handlePageShow);
        window.removeEventListener('pagehide', handlePageHide);
        window.removeEventListener('orientationchange', () => {});

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

        // Clean up bearing update timeout
        if (bearingUpdateTimeout) {
            clearTimeout(bearingUpdateTimeout);
        }

        // Clean up optimized marker system
        optimizedMarkerSystem.destroy();

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

    $: arrow_radians = ($bearingState.bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;

    // Tile provider configuration
    // Set initial tile provider (can be changed via setTileProvider() function)
    setTileProvider('OpenStreetMap.Mapnik');//TracesTrack.Topo');

    // Get the current provider configuration reactively
    $: tileConfig = getCurrentProviderConfig();

    // Force tile layer to update when provider changes
    $: if ($currentTileProvider) {
        tileConfig = getCurrentProviderConfig();
    }

    // Reactive updates for spatial changes (new photos from worker)
    // Combine visible photos with placeholder photos for marker rendering
    $: allPhotosForMarkers = [...($visiblePhotos || []), ...($placeholderPhotos || [])];

    $: if (allPhotosForMarkers && map) {
        console.log(`🢄Map: Reactive update triggered - updating markers with ${$visiblePhotos?.length || 0} visible photos + ${$placeholderPhotos?.length || 0} placeholder photos = ${allPhotosForMarkers.length} total`);
        updateOptimizedMarkers(allPhotosForMarkers);
    }

    // Ultra-fast bearing color updates (no worker communication)
    $: if ($bearingState && currentMarkers && currentMarkers.length > 0) {
        optimizedMarkerSystem.scheduleColorUpdate($bearingState.bearing);
    }

</script>


<!-- The map container -->
<div bind:clientHeight={height} bind:clientWidth={width} class="map">
    <LeafletMap
            bind:this={elMap}
            events={{moveend: mapStateUserEvent, zoomend: mapStateUserEvent}}
            options={{
				attributionControl: false, // We'll add it manually with correct position
                center: [$spatialState.center.lat, $spatialState.center.lng],
                zoom: $spatialState.zoom,
                minZoom: 3,
                maxZoom: 23,
                // @ts-ignore - maxNativeZoom is a valid Leaflet option
                maxNativeZoom: 19,
                zoomControl: false, // We'll add it manually in the right order
                scrollWheelZoom: !/Android/i.test(navigator.userAgent), // Disable on Android, we'll handle it manually
                touchZoom: true,
                dragging: true,
                bounceAtZoomLimits: true,
                // Memory optimization settings
                preferCanvas: true, // Use Canvas renderer for better performance
                maxBoundsViscosity: 1.0 // Prevent excessive panning
            }}
    >

        <ScaleControl options={{maxWidth: 100, imperial: false}} position="topleft"/>

        <!-- Base map tiles
         -->

        {#key $currentTileProvider}
        <TileLayer
                options={{
                    attribution: tileConfig.attribution, // Attribution goes in options
                    maxZoom: tileConfig.maxZoom,
                    maxNativeZoom: tileConfig.maxNativeZoom,
                    minZoom: tileConfig.minZoom || 3,
                    // Memory optimization for tiles
                    //keepBuffer: 1, // Keep fewer tiles in memory (default is 2)
                    //updateWhenIdle: false, // Update tiles only when panning ends
                    //updateWhenZooming: false, // Don't update during zoom animation
                    tileSize: tileConfig.tileSize || 256, // Standard tile size
                    zoomOffset: tileConfig.zoomOffset || 0,
                    detectRetina: tileConfig.detectRetina !== undefined ? tileConfig.detectRetina : false,
                    crossOrigin: tileConfig.crossOrigin !== undefined ? tileConfig.crossOrigin : true,
                    // Additional performance options
                    updateInterval: 100, // Throttle tile updates
                    tms: tileConfig.tms || false,
                    noWrap: tileConfig.noWrap !== undefined ? tileConfig.noWrap : true,
                    zoomReverse: tileConfig.zoomReverse || false,
                    opacity: tileConfig.opacity !== undefined ? tileConfig.opacity : 1,
                    zIndex: tileConfig.zIndex || 1,
                    bounds: tileConfig.bounds, // Respect provider bounds if specified
                    className: 'map-tiles'
                }}
                url={tileConfig.url}
        />
        {/key}


        {#if $spatialState.center}
            <Circle
                    latLng={$spatialState.center}
                    radius={$spatialState.range}
                    color="#4AE092"
                    fillColor="#4A90E2"
                    weight={1.8}
            />
            <!-- arrow -->
        {/if}

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


    <!-- Debug bounds rectangle -->
    <!--{#if $app.debug > 0 && $spatialState.bounds}-->
    <!--    <Polygon-->
    <!--            latLngs={[-->
    <!--                [$spatialState.bounds.top_left.lat, $spatialState.bounds.top_left.lng],-->
    <!--                [$spatialState.bounds.top_left.lat, $spatialState.bounds.bottom_right.lng],-->
    <!--                [$spatialState.bounds.bottom_right.lat, $spatialState.bounds.bottom_right.lng],-->
    <!--                [$spatialState.bounds.bottom_right.lat, $spatialState.bounds.top_left.lng]-->
    <!--            ]}-->
    <!--            color="#FF0000"-->
    <!--            fillColor="#FF0000"-->
    <!--            fillOpacity={0.1}-->
    <!--            weight={2}-->
    <!--            dashArray="5, 10"-->
    <!--        />-->
    <!--{/if}-->


    </LeafletMap>
<div class="provider-selector-container">
    <TileProviderSelector />
</div>

</div>

<!-- Debug bounds info -->
<!--{#if $app.debug > 0 && $spatialState.bounds}-->
<!--    <div class="debug-bounds-info">-->
<!--        <div>Bounds:</div>-->
<!--        <div>NW: {$spatialState.bounds.top_left.lat.toFixed(6)}, {$spatialState.bounds.top_left.lng.toFixed(6)}</div>-->
<!--        <div>SE: {$spatialState.bounds.bottom_right.lat.toFixed(6)}, {$spatialState.bounds.bottom_right.lng.toFixed(6)}</div>-->
<!--        <div>Width: {($spatialState.bounds.bottom_right.lng - $spatialState.bounds.top_left.lng).toFixed(6)}°</div>-->
<!--        <div>Height: {($spatialState.bounds.top_left.lat - $spatialState.bounds.bottom_right.lat).toFixed(6)}°</div>-->
<!--    </div>-->
<!--{/if}-->

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
                disabled={!$photoToLeft}
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
                disabled={!$photoToRight}
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
        class={$locationTracking ? 'active' : ''}
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
        title="Auto bearing updates ({$bearingMode === 'car' ? 'GPS' : 'compass'} mode)"
        disabled={$bearingMode === 'walking' && !$compassAvailable}
    >
        <Compass />
    </button>
    <button
        class="bearing-mode-button { $bearingMode === 'car' ? 'car-mode' : 'walking-mode' }"
        on:click={(e) => handleButtonClick('bearing-mode', e)}
        title={$bearingMode === 'car' ? 'Car mode: GPS bearing' : 'Walking mode: Compass bearing'}
    >
        {#if $bearingMode === 'car'}
            <Car />
        {:else}
            <PersonStanding />
        {/if}
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
                title={`Toggle ${source.name} photos`}
                data-testid={`source-toggle-${source.id}`}
        >
            <div class="source-icon-wrapper">
                <Spinner show={source.enabled && (source.type === 'stream' ? $sourceLoadingStatus[source.id]?.isLoading || false : !!(source.requests && source.requests.length))} color="#fff"></Spinner>
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
        /*background-color: rgba(255, 255, 255, 0.1);*/
    }

 .source-buttons-container.compact button {
    opacity: 0.7;
}

.source-buttons-container:not(.compact) button {
    opacity: 1;
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

    .location-button-container button {
        opacity: 0.6;
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

    .provider-selector-container {
        position: absolute;
        bottom: 15px;
        left: 10px;
        z-index: 30000;
    }

	.bearing-mode-button.car-mode {
		background-color: #ff5722;
	}

	.bearing-mode-button.walking-mode {
		background-color: #4285F4;
	}

</style>
