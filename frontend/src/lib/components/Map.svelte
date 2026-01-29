<script lang="ts">
    import {onMount, onDestroy, tick} from 'svelte';
    import {LeafletMap, TileLayer, Marker, Circle, ScaleControl} from 'svelte-leafletjs';
    import {LatLng} from 'leaflet';
    import {RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle, MapPin, Pause, ArrowUp, ArrowDown, Layers, Eye, Map as MapIcon, Info} from 'lucide-svelte';
    import L from 'leaflet';
    import 'leaflet/dist/leaflet.css';
    import { getCurrentProviderConfig, setTileProvider, currentTileProvider } from '$lib/tileProviders';
    import Spinner from './Spinner.svelte';
    import TileProviderSelector from './TileProviderSelector.svelte';
    import CompassButton from './CompassButton.svelte';
    import CompassModeMenu from './CompassModeMenu.svelte';
    import { getCurrentPosition, type GeolocationPosition } from '$lib/preciseLocation';
	import {
		disableLocationTracking,
		enableLocationTracking,
		locationManager,
		locationTrackingLoading,
		startLocationTracking,
		stopLocationTracking
	} from '$lib/locationManager';
	import SpatialStateArrow from './SpatialStateArrow.svelte';

	import {
		spatialState,
		bearingState,
		visiblePhotos,
		photoToLeft,
		photoToRight,
		photosInArea,
		photosInRange,
		updateSpatialState,
		updateBearingByDiff,
		updateBearingWithPhoto,
		bearingMode,
		type BearingMode, updateBearing,
	} from "$lib/mapState";
	import {enableSourceForPhotoUid, sources} from "$lib/data.svelte.js";
    import { simplePhotoWorker } from '$lib/simplePhotoWorker';
    import { turn_to_photo_to, app, sourceLoadingStatus } from "$lib/data.svelte.js";
    import { updateGpsLocation, setLocationTracking, setLocationError, gpsLocation, locationTracking } from "$lib/location.svelte.js";
    import { isOnMapRoute, compassEnabled, disableCompass } from "$lib/compass.svelte.js";
    import { optimizedMarkerSystem, setupMarkerClickDelegation } from '$lib/optimizedMarkers';
    import '$lib/styles/optimizedMarkers.css';
    import type { PhotoData } from '$lib/types/photoTypes';
	import PhotoMarkerIcon from './PhotoMarkerIcon.svelte';

    import {get} from "svelte/store";
	import SpatialStateArrowIcon from "$lib/components/SpatialStateArrowIcon.svelte";
	import {stringifyCircularJSON} from "$lib/utils/json";
	import {TAURI} from "$lib/tauri";
	import {parsePhotoUid} from "$lib/urlUtilsServer";
	import {openExternalUrl} from "$lib/urlUtils";
	import InsetGradients from "$lib/components/InsetGradients.svelte";

	export let update_url = false;

    let flying = false;
    let programmaticMove = false; // Flag to prevent position sync conflicts

    let locationApiEventFlashTimer: any = null;
    let locationApiEventFlash = false;

    // GPS orientation tracking for car mode
    // When in car mode with compass enabled, we track GPS heading changes
    // and apply the difference to the map bearing (not absolute positioning)
    let lastGpsHeading: number | null = null;
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

    // Compass state is now managed by stores in compass.svelte.ts

    // Optimized marker system variables
    let currentMarkers: L.Marker[] = [];
    let lastPhotosUpdate = 0;

    // Location tracking re-enable timer
    let locationReEnableTimer: number | null = null;


    // Flag to track if the current map event was caused by zoom buttons
    let isZoomButtonEvent = false;
	let isActivityOrientationChangeEvent = false;
	let isWindowResizeEvent = false;

    let zoomButtonEventTimer: number | null = null;
	let activityOrientationChangeTimer: number | null = null;
	let windowResizeTimer: number | null = null;


    // Debug bounds rectangle
    let boundsRectangle: any = null;
    let userHeading: number | null = null;
    let userLocation: GeolocationPosition | null = null;

    // Source buttons display mode
    let compactSourceButtons = true;

    // Attribution popup state (mobile only)
    let showAttribution = false;
    let useCompactAttribution = false; // Set on mount based on screen width

    // Handle clicks in attribution popup - open links externally, otherwise close
    async function handleAttributionClick(event: Event) {
        const link = (event.target as HTMLElement).closest('a') as HTMLAnchorElement;
        if (link?.href) {
            event.preventDefault();
            await openExternalUrl(link.href);
        } else {
            showAttribution = false;
        }
    }

    // Compass mode menu state
    let compassMenuVisible = false;
    let compassMenuPosition = { top: 0, right: 0 };

    function handleCompassShowMenu(event: CustomEvent<{ buttonRect: DOMRect }>) {
        const rect = event.detail.buttonRect;
        compassMenuPosition = {
            top: rect.bottom + 2,
            right: window.innerWidth - rect.right
        };
        compassMenuVisible = true;
    }

    function handleCompassHideMenu() {
        compassMenuVisible = false;
    }

    let compassButtonRef: any;

    function handleCompassSelectMode(event: CustomEvent<{ mode: BearingMode }>) {
        // Forward the event back to CompassButton to handle the logic
        compassButtonRef?.selectMode(event.detail.mode);
        compassMenuVisible = false;
    }


    $: map = elMap?.getMap();

	let invalidateSizeTimeout: any = null;

    // Track if marker click delegation has been set up
    let markerClickDelegationSetup = false;

    // Expose map to window for testing and fix initial size
    $: if (map && typeof window !== 'undefined') {
        (window as any).leafletMap = map;

        // Set up marker click event delegation (once)
        if (!markerClickDelegationSetup) {
            const container = map.getContainer();
            if (container) {
                setupMarkerClickDelegation(container);
                markerClickDelegationSetup = true;
                console.log('🢄Map: Marker click delegation set up');
            }
        }
        // console.log('🢄Map reactive: map available, current center:', JSON.stringify(map.getCenter()));
        // console.log('🢄Map reactive: spatialState center:', JSON.stringify(get(spatialState).center));
        // console.log('🢄Map reactive: spatialState bounds:', JSON.stringify(get(spatialState).bounds));

        // Fix initial map size after the map becomes available
		if (!invalidateSizeTimeout) {
			invalidateSizeTimeout = setTimeout(() => {
				// console.log('🢄Map setTimeout: before invalidateSize, map center:', JSON.stringify(map?.getCenter()));
				// Guard against race conditions where map is destroyed before timeout fires
				try {
					if (map && map._loaded && map.getContainer() && map.invalidateSize) {
						console.log('🢄Fixing initial map size');
						map.invalidateSize({ reset: true, animate: false });
						console.log('🢄Map setTimeout: after invalidateSize, map center:', JSON.stringify(map?.getCenter()));
					}
				} catch (e) {
					// Map may have been destroyed or is in an inconsistent state
					console.debug('🢄Map invalidateSize skipped:', e instanceof Error ? e.message : String(e));
				}
				afterInit();
	        }, 200);
		}
    }

	async function afterInit() {
		// console.log('🢄Map afterInit');
		// console.log('🢄Map afterInit: current spatialState center:', JSON.stringify(get(spatialState).center));
		// console.log('🢄Map afterInit: current map center:', JSON.stringify(map?.getCenter()));
		await tick();

		const urlParams = new URLSearchParams(window.location.search);
		const lat = urlParams.get('lat');
		const lon = urlParams.get('lon');
		const zoom = urlParams.get('zoom');
		const bearingParam = urlParams.get('bearing');
		const photoParam = urlParams.get('photo');

		// Create a fresh object - don't mutate the store's internal state
		const oldState = get(spatialState);
		let p = {
			center: oldState.center,
			zoom: oldState.zoom,
			bounds: oldState.bounds,
			range: oldState.range,
			source: oldState.source
		};
		let positionChanged = false;

		if (lat && lon) {
			console.log('🢄Setting position to', lat, lon, 'from URL');
			p.center = new LatLng(parseFloat(lat), parseFloat(lon));
			positionChanged = true;
		}

		if (zoom) {
			console.log('🢄Setting zoom to', zoom, 'from URL');
			p.zoom = parseFloat(zoom);
			positionChanged = true;
		}

		// Move the map FIRST if position changed from URL params
		if (positionChanged && map) {
			map.setView(p.center, p.zoom, { animate: false });
			// Wait for the map to settle before getting bounds
			await new Promise<void>(resolve => {
				map.once('moveend', () => resolve());
				// Fallback timeout in case moveend doesn't fire
				setTimeout(resolve, 100);
			});
		}

		// Now get bounds AFTER the map has moved
		let bounds = map.getBounds();
		console.log('🢄Leaflet bounds after move:', JSON.stringify(bounds));
		if (bounds == null || bounds.getNorthWest().lat === bounds.getSouthEast().lat || bounds.getNorthWest().lng === bounds.getSouthEast().lng) {
			console.log('🢄leaflet bounds are invalid, using fallback')
			bounds = new L.LatLngBounds(
				new L.LatLng(p.center.lat - 0.0001, p.center.lng - 0.0001),
				new L.LatLng(p.center.lat + 0.0001, p.center.lng + 0.0001)
			);
		}
		p.bounds = {
			top_left: bounds.getNorthWest(),
			bottom_right: bounds.getSouthEast()
		};

		await updateSpatialState({...p}, 'map');

		// Handle photo parameter and enable corresponding source
		const photoUid = parsePhotoUid(photoParam);
		if (photoUid) {
			console.log('🢄Photo parameter from URL:', photoUid);
			enableSourceForPhotoUid(photoUid);
			// Switch to view mode when opening a specific photo
			app.update(a => ({...a, activity: 'view'}));
		}

		if (bearingParam) {
			console.log('🢄Setting bearing to', bearingParam, 'from URL');
			const bearing = parseFloat(bearingParam);
			updateBearing(bearing, 'url', photoUid ?? undefined);
		}

		setTimeout(() => {
			update_url = true;
		}, 100);
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

		//console.log(`spatialState: ${stringifyCircularJSON(spatial)}`);

        if (!map || programmaticMove) return;
        try {
            // Check if map is fully initialized with container
            if (!map.getContainer() || !map._loaded) return;

            const currentCenter = map.getCenter();
            const currentZoom = map.getZoom();
            if (!currentCenter || currentCenter.lat !== spatial.center.lat || currentCenter.lng !== spatial.center.lng || currentZoom !== spatial.zoom) {
                //console.log('🢄setView', JSON.stringify(spatial.center), spatial.zoom);
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
	let seenFirstMoveEnd = false;

    async function mapStateUserEvent(event: any) {

		if (event.type == 'moveend')
		{
			if (!seenFirstMoveEnd)
			{
				seenFirstMoveEnd = true;
				return;
			}
		}

		if (TAURI && event.type == 'moveend')
		{
			return // ignore moveend in android, as those fire off even when the map is moved programmatically - there's no way to distinguish user-initiated location changes from programmatic (gps). The tradeoff is that keyboard cant be used. Mouse/touch works by triggering dragend.
		}

		console.log('🢄🗺mapStateUserEvent:', stringifyCircularJSON(event.type));

        if (!flying) {
            let _center = map.getCenter();
            let p = get(spatialState);

            if (p.center.lat != _center.lat || p.center.lng != _center.lng) {
                console.log('🢄p.center:', JSON.stringify(p.center), '_center:', JSON.stringify(_center));

                // Only disable location tracking if this wasn't caused by zoom buttons
                if (!isZoomButtonEvent) {
                    console.log('🢄disableLocationTracking');
                    disableLocationTracking();
                } else {
                    console.log('🢄Zoom button event detected - not disabling location tracking');
                }
            }
			await onMapStateChange(true, 'mapStateUserEvent');
        }
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
            // console.log('🢄onMapStateChange: force:', force, 'reason:', reason, 'center:', JSON.stringify(_center), 'zoom:', _zoom);

            const currentSpatial = get(spatialState);
            const bounds = map.getBounds();
            const range = get_range(_center);

			// console.log(`🢄Map: currentSpatial`, JSON.stringify(currentSpatial));
			// console.log(`🢄Map: bounds`, JSON.stringify(bounds));
			// console.log(`🢄Map: range`, range);

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

        // Disable compass tracking when any turn button is clicked (but keep GPS orientation)
        if (action === 'left' || action === 'right' || action === 'rotate-ccw' || action === 'rotate-cw') {
            if ($compassEnabled) {
                console.log('🢄🧭 Disabling compass tracking due to manual turn');
                disableCompass();
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

    /**
     * Handle marker click - navigate to clicked photo
     * If photo is not in range, move the map to the photo's location first
     */
    function handleMarkerClick(photo: PhotoData) {
        console.log('🢄Marker clicked:', photo.uid, 'at', photo.coord);

        // Check if photo is already in photosInRange
        const inRange = get(photosInRange);
        const isInRange = inRange.some(p => p.uid === photo.uid);

        if (isInRange) {
            // Photo is in range, just update bearing to select it
            console.log('🢄Photo in range, selecting directly');
            updateBearingWithPhoto(photo, 'marker_click');
        } else {
            // Photo is not in range, move map to photo location first
            console.log('🢄Photo not in range, moving map to photo location');

            // Set flag to prevent position sync conflicts
            programmaticMove = true;

            // Move map to photo location
            const newCenter = new LatLng(photo.coord.lat, photo.coord.lng);
            map.flyTo(newCenter, map.getZoom());

            // Update spatial state
            updateSpatialState({
                center: newCenter,
                zoom: map.getZoom(),
                bounds: null,
            });

            // Update bearing to the photo (this stores photoUid so it will be selected once in range)
            updateBearingWithPhoto(photo, 'marker_click');

            // Reset flag after animation
            setTimeout(() => {
                programmaticMove = false;
            }, 1000);
        }
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


    // Handle GPS location updates only (position/coordinates)
    async function handleGpsLocationUpdate(position: GeolocationPosition) {
        const { latitude, longitude, accuracy } = position.coords;

        // Store the location data locally
        userLocation = position;

        //console.log("handleGpsLocationUpdate:", latitude, longitude, accuracy);
        locationTrackingLoading.set(false);
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

        // Set up marker click handler
        optimizedMarkerSystem.setOnMarkerClick(handleMarkerClick);

        // Signal that we're now on map route
        isOnMapRoute.set(true);

        // Initialize the simplified photo worker (async)
        (async () => {
            try {
                await simplePhotoWorker.initialize();
                //console.log('🢄SimplePhotoWorker initialized successfully');
            } catch (error) {
                console.error('🢄Failed to initialize SimplePhotoWorker:', error);
            }

            /*await onMapStateChange(true, 'mount');
            console.log('🢄Map component mounted - after onMapStateChange');*/

            // Add zoom control after scale control for proper ordering
            const zoomControl = new L.Control.Zoom({ position: 'topleft' });
            map.addControl(zoomControl);

            // Add attribution control at bottom-left (desktop only)
            // On mobile/narrow screens, use compact (i) button instead
            useCompactAttribution = window.innerWidth < 768;
            if (!useCompactAttribution) {
                const attributionControl = new L.Control.Attribution({ position: 'bottomleft' });
                map.addControl(attributionControl);
            }

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

    //import.meta.hot?.dispose(() => (map = null));

    onDestroy(async () => {
        console.log('🢄Map component destroyed');
		if (invalidateSizeTimeout) {
			clearTimeout(invalidateSizeTimeout);
			invalidateSizeTimeout = null;
		}
		// Clear cached photos and reset bounds so we fetch fresh data when map remounts
		photosInArea.set([]);
		spatialState.update(s => ({...s, bounds: null}));
        // Signal that we're no longer on map route
        isOnMapRoute.set(false);
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

        // Clean up location API event flash timer
        if (locationApiEventFlashTimer) {
            clearTimeout(locationApiEventFlashTimer);
            locationApiEventFlashTimer = null;
        }

        // Clean up optimized marker system
        optimizedMarkerSystem.destroy();

        // Clean up tile pruning interval
        /*if (tilePruneInterval) {
            clearInterval(tilePruneInterval);
            tilePruneInterval = null;
        }*/

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

    // Invalidate map size when container dimensions change (e.g., split layout settling)
    $: if (width && height && map) {
        map.invalidateSize({ animate: false });
    }

    // For the bearing overlay arrow:
    let centerX: number;
    $: centerX = width / 2;
    let centerY: number;
    $: centerY = height / 2;
    let arrowLength = fov_circle_radius_px;

    let arrow_radians;
    let arrowX;
    let arrowY;

    $: arrow_radians = ($bearingState.bearing - 90) * Math.PI / 180; // shift so 0° points "up"
    $: arrowX = centerX + Math.cos(arrow_radians) * arrowLength;
    $: arrowY = centerY + Math.sin(arrow_radians) * arrowLength;

    // Get the current provider configuration reactively
    $: tileConfig = getCurrentProviderConfig();

    // Force tile layer to update when provider changes
    $: if ($currentTileProvider) {
        tileConfig = getCurrentProviderConfig();
    }

    // Reactive updates for spatial changes (photos from worker include filtered placeholders)
    $: if ($visiblePhotos && map) {
        //console.log(`🢄Map: Reactive update triggered - updating markers with ${$visiblePhotos.length} total photos`);
        updateOptimizedMarkers($visiblePhotos);
    }

    // Ultra-fast bearing color updates (no worker communication)
    $: if ($bearingState && currentMarkers && currentMarkers.length > 0) {
		if ($app.activity != 'capture')
		{
        	optimizedMarkerSystem.scheduleColorUpdate($bearingState.bearing);
		}
    }

</script>


<!-- The map container -->
<div bind:clientHeight={height} bind:clientWidth={width} class="map">
    <LeafletMap
            bind:this={elMap}
            events={
            	{
					moveend: mapStateUserEvent,
					zoomend: mapStateUserEvent,
	            	dragend: mapStateUserEvent,
    	        	dragstart: (e) => {disableLocationTracking()},
    	        	//movestart: (e) => {console.log('🗺movestart', stringifyCircularJSON(e))},
            	}
            	}
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


        {#if ($app.activity != 'capture') && $spatialState.center}
            <Circle
                    latLng={$spatialState.center}
                    radius={$spatialState.range}
                    color="#4AE092"
                    fillColor="#ffffff"
                    weight={1.8}
					dashArray={[5, 15]}
            />
            <!-- arrow -->
        {/if}

        <div class="svg-overlay">

 			<SpatialStateArrow
				{width}
				{height}
				{centerX}
				{centerY}
				{arrowX}
				{arrowY}
			/>

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

{#if useCompactAttribution}
    <button
        class="attribution-info-button"
        on:click={() => showAttribution = !showAttribution}
        title="Map attribution"
    >
        <Info size={18} />
    </button>
    {#if showAttribution}
        <div
            class="attribution-popup"
            role="dialog"
            aria-label="Map attribution"
            tabindex="-1"
            on:click={handleAttributionClick}
            on:keydown={(e) => e.key === 'Escape' && (showAttribution = false)}
        >
            {@html tileConfig.attribution || '© OpenStreetMap contributors'}
        </div>
    {/if}
{/if}

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
<!--        <button-->
<!--                on:click={async (e) => {await handleButtonClick('left', e)}}-->
<!--                on:mousedown={(e) => handleMouseDown('left', e)}-->
<!--                on:mouseup={handleMouseUp}-->
<!--                on:mouseleave={handleMouseUp}-->
<!--                title={slideshowActive && slideshowDirection === 'left' ?-->
<!--                      "Stop slideshow" :-->
<!--                      "Rotate to next photo on the left (long press for slideshow)"}-->

<!--                class:slideshow-active={slideshowActive && slideshowDirection === 'left'}-->
<!--        >-->
<!--            {#if slideshowActive && slideshowDirection === 'left'}-->
<!--                <Pause />-->
<!--            {:else}-->
<!--                <PhotoMarkerIcon bearing={-90} />-->
<!--            {/if}-->
<!--        </button>-->

        <button
                on:click={async (e) => {await handleButtonClick('rotate-ccw', e)}}
                title="Rotate view 15° counterclockwise"
        >
            <SpatialStateArrowIcon centerX={8} centerY={8} arrowX={5} arrowY={2} />
        </button>

        <button
                on:click={(e) => handleButtonClick('forward', e)}
                title="Move forward in viewing direction"
        >

			<SpatialStateArrowIcon centerX={8} centerY={8} arrowX={8} arrowY={0} />

        </button>

        <button
                on:click={(e) => handleButtonClick('backward', e)}
                title="Move backward"
        >

			<SpatialStateArrowIcon centerX={8} centerY={8} arrowX={8} arrowY={16} />

        </button>

        <button
                on:click={(e) => handleButtonClick('rotate-cw', e)}
                title="Rotate view 15° clockwise"
        >
            <SpatialStateArrowIcon centerX={8} centerY={8} arrowX={11} arrowY={2} />
        </button>

<!--        <button-->
<!--                on:click={(e) => handleButtonClick('right', e)}-->
<!--                on:mousedown={(e) => handleMouseDown('right', e)}-->
<!--                on:mouseup={handleMouseUp}-->
<!--                on:mouseleave={handleMouseUp}-->
<!--                title={slideshowActive && slideshowDirection === 'right' ?-->
<!--                      "Stop slideshow" :-->
<!--                      "Rotate to next photo on the right (long press for slideshow)"}-->
<!--                class:slideshow-active={slideshowActive && slideshowDirection === 'right'}-->
<!--        >-->
<!--            {#if slideshowActive && slideshowDirection === 'right'}-->
<!--                <Pause />-->
<!--            {:else}-->
<!--                <PhotoMarkerIcon bearing={90} />-->
<!--            {/if}-->
<!--        </button>-->
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
        {#if $locationTrackingLoading}
            <Spinner show={true} color="#4285F4"></Spinner>
        {/if}
    </button>
    <CompassButton bind:this={compassButtonRef} on:showMenu={handleCompassShowMenu} on:hideMenu={handleCompassHideMenu} />
</div>

<div class="source-buttons-container" class:compact={compactSourceButtons}>
    {#each $sources as source}
        <button

                class=" source-button {source.enabled ? 'active' : ''}"
                on:click={() => toggleSourceVisibility(source.id)}
                title={`Toggle ${source.name} photos`}
                data-testid={`source-toggle-${source.id}`}
        >
            <div class="source-icon-wrapper">
                <Spinner show={source.enabled && ($sourceLoadingStatus[source.id]?.is_loading || false)} color="#fff"></Spinner>
                <div class="source-icon" style="background-color: {source.color}"></div>
            </div>
			{#if !compactSourceButtons}
                {source.name}
				{:else}
				{source.name.charAt(0)}..
			{/if}
        </button>
    {/each}
    <button
        class="toggle-compact {compactSourceButtons ? 'active' : ''}"
        on:click={() => compactSourceButtons = !compactSourceButtons}
        title={compactSourceButtons ? "Show labels" : "Hide labels"}
    >
        ...
    </button>
</div>

<style>




    .map {
        width: 100%;
        height: 100%;
        position: relative;
    }


    .control-buttons-container {
        position: absolute;
        bottom: var(--safe-area-inset-bottom, 0px);
        right: calc(0px + var(--safe-area-inset-right, 0px));
        z-index: 30000;
        pointer-events: none; /* This makes the container transparent to mouse events */
    }

    .buttons {
        display: flex;
        gap: 0.5rem;
        background-color: rgba(255, 255, 255, 0.1);
        padding: 0rem;
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

/*    .buttons button.slideshow-active {
        background-color: #4285F4;
        color: white;
        border-color: #3367d6;
        animation: pulse 2s infinite;
    }
*/
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
        top: calc(6px + var(--safe-area-inset-top, 0px));
        right: calc(6px + var(--safe-area-inset-right, 0px));
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
        top: calc(90px + var(--safe-area-inset-top, 0px));
        right: calc(6px + var(--safe-area-inset-right, 0px));
        z-index: 30000;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        margin: 0;
        padding: 0;
		text-overflow: ellipsis;
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
        pointer-events: none;
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
        background-color: #ddd !important;
        color: black !important;
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
        top: 115px;
        left: 10px;
        z-index: 30000;
		background-color: rgba(255, 255, 255, 0.5);
    }

    .attribution-info-button {
        position: absolute;
        top: 155px;
        left: 10px;
        z-index: 30000;
        width: 32px;
        height: 32px;
        border: 1px solid #ccc;
        border-radius: 4px;
        background-color: rgba(255, 255, 255, 0.7);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .attribution-info-button:hover {
        background-color: rgba(255, 255, 255, 0.9);
    }

    .attribution-popup {
        position: absolute;
        top: 190px;
        left: 10px;
        z-index: 30001;
        max-width: 280px;
        padding: 8px 12px;
        background-color: rgba(255, 255, 255, 0.95);
        border: 1px solid #ccc;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        font-size: 11px;
        line-height: 1.4;
        cursor: pointer;
    }

    .attribution-popup :global(a) {
        color: #0078a8;
        text-decoration: none;
    }

    .attribution-popup :global(a:hover) {
        text-decoration: underline;
    }


</style>

<!-- Compass mode menu at top level to escape stacking contexts -->
<CompassModeMenu
    visible={compassMenuVisible}
    position={compassMenuPosition}
    on:selectMode={handleCompassSelectMode}
    on:close={handleCompassHideMenu}
/>
