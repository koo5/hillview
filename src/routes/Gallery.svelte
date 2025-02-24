<script>
    import { ChevronDown, ChevronUp, Download, AlertCircle, RefreshCw } from 'lucide-svelte';
    // Example import; adjust paths as needed
    import { geoPicsUrl } from '../data.js';

    // Props from parent
    export let photos = [];    // array of PhotoData
    export let mapState = {};  // MapState

    // Constants / Config
    const FOV_ANGLE = 60;
    const MAX_RELATIVE_ANGLE = 30;
    const DOWNLOAD_TIMEOUT = 30000;
    const MAX_VISIBLE_PHOTOS = 3;
    const MAX_HORIZONTAL_OFFSET = 25;

    // Retry logic
    const MAX_RETRIES = 5;
    const INITIAL_RETRY_DELAY = 1000; // ms
    const MAX_RETRY_DELAY = 32000;    // ms

    // Local component state
    let showDebug = false;
    let downloadError = null;
    let downloadingPhoto = null;

    // Loading states: { [photoId]: { attempts: number, timeout: number | null } }
    let loadingStates = {};

    // For storing references to each <img> element
    let imageRefs = {};

    // Helper function to emulate "functional updates" for loadingStates
    function setLoadingStates(updater) {
        // 'updater' is a callback like prev => { ... }
        const newState = updater(loadingStates);
        loadingStates = newState;
    }

    // Distance between two lat/lng points (in km)
    function calculateDistance(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a =
            Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // Bearing between two lat/lng points (0..360)
    function calculateBearing(lat1, lon1, lat2, lon2) {
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const lat1Rad = lat1 * Math.PI / 180;
        const lat2Rad = lat2 * Math.PI / 180;

        const y = Math.sin(dLon) * Math.cos(lat2Rad);
        const x =
            Math.cos(lat1Rad) * Math.sin(lat2Rad) -
            Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);

        let bearing = Math.atan2(y, x) * (180 / Math.PI);
        return (bearing + 360) % 360;
    }

    // Calculate the 3D-ish position of the photo in the gallery
    function calculatePhotoPosition(distance, relativeBearing, maxDistance) {
        const normalizedDistance = Math.min(distance, maxDistance) / maxDistance;

        // We “squeeze” bearings to get a curved distribution within ±FOV_ANGLE/2
        const normalizedBearing = relativeBearing / (FOV_ANGLE / 2); // -1..1
        const x =
            Math.sign(normalizedBearing) *
            Math.pow(Math.abs(normalizedBearing), 1.5) *
            MAX_HORIZONTAL_OFFSET *
            0.25;

        // Vertical offset (closer = higher in the view)
        const y = normalizedDistance * 40;

        // Scale factor (closer = bigger)
        const scale = 1 + (1 - normalizedDistance) * 0.7;

        // z-index (closer = on top)
        const z = Math.floor((1 - normalizedDistance) * 1000);

        return { x, scale, z, y };
    }

    // Initiate retry logic for a photo
    function retryLoad(photo) {
        const state = loadingStates[photo.id] || { attempts: 0, timeout: null };

        if (state.attempts >= MAX_RETRIES) {
            console.error(`Max retries (${MAX_RETRIES}) reached for photo:`, photo.file);
            return;
        }

        // Clear any existing timeout
        if (state.timeout) {
            clearTimeout(state.timeout);
        }

        // Exponential backoff
        const delay = Math.min(
            INITIAL_RETRY_DELAY * Math.pow(2, state.attempts),
            MAX_RETRY_DELAY
        );

        const timeoutId = window.setTimeout(() => {
            const imgEl = imageRefs[photo.id];
            if (imgEl) {
                const currentSrc = imgEl.src;
                // Force reload by resetting src
                imgEl.src = '';
                imgEl.src = currentSrc;
            }
        }, delay);

        setLoadingStates(prev => ({
            ...prev,
            [photo.id]: {
                attempts: state.attempts + 1,
                timeout: timeoutId
            }
        }));
    }

    // Computed / derived data
    let visiblePhotos = [];
    let totalInCircle = 0;

    // Svelte reactive statement (runs whenever `photos` or `mapState` changes)
    $: {
        // 1) Photos within the circle (distance <= maxDistance)
        const inCircle = photos.filter((photo) => {
            const dist = calculateDistance(
                mapState.center[0],
                mapState.center[1],
                photo.latitude,
                photo.longitude
            );
            return dist <= mapState.maxDistance;
        });

        // 2) Among those, figure out which are in the FOV
        const visible = inCircle
            .map((photo) => {
                const dist = calculateDistance(
                    mapState.center[0],
                    mapState.center[1],
                    photo.latitude,
                    photo.longitude
                );

                const brng = calculateBearing(
                    mapState.center[0],
                    mapState.center[1],
                    photo.latitude,
                    photo.longitude
                );

                // relative bearing ( -180..180 ) from viewer’s bearing
                let relativeBearing = (brng - mapState.bearing + 360) % 360;
                if (relativeBearing > 180) relativeBearing -= 360;

                // camera direction difference
                const directionDiff = Math.abs(
                    ((photo.direction - mapState.bearing + 180 + 360) % 360) - 180
                );

                // position in the gallery
                const { x, y, scale, z } = calculatePhotoPosition(dist, relativeBearing, mapState.maxDistance);

                return {
                    ...photo,
                    distance: dist,
                    relativeBearing,
                    directionDiff,
                    x,
                    y,
                    scale,
                    z,
                    visible:
                        Math.abs(relativeBearing) <= FOV_ANGLE / 2 &&
                        directionDiff <= MAX_RELATIVE_ANGLE
                };
            })
            .filter((p) => p.visible)
            .sort((a, b) => {
                // sort by directionDiff, then by distance
                const diffA = a.directionDiff || 0;
                const diffB = b.directionDiff || 0;
                if (diffA !== diffB) {
                    return diffA - diffB;
                }
                return (a.distance || 0) - (b.distance || 0);
            })
            .slice(0, MAX_VISIBLE_PHOTOS);

        visiblePhotos = visible;
        totalInCircle = inCircle.length;
    }

    // Download a photo with a 30s timeout
    async function handleDownload(photo) {
        if (downloadingPhoto === photo.file) return;

        downloadingPhoto = photo.file;
        downloadError = null;

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT);

            const response = await fetch(`${geoPicsUrl}/${encodeURIComponent(photo.file)}`, {
                signal: controller.signal,
                headers: {
                    Accept: 'image/jpeg'
                }
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = photo.file;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (err) {
            console.error('Error downloading photo:', err);
            downloadError =
                err instanceof Error ? err.message : 'Failed to download photo';
        } finally {
            downloadingPhoto = null;
        }
    }
</script>

<!-- Main layout -->
<div class="h-full flex flex-col">
    <!-- Header -->
    <div class="p-4 bg-gray-50 border-b flex justify-between items-center">
        <div>
            <h2 class="text-lg font-semibold">Visible Photos ({totalInCircle})</h2>
            <p class="text-sm text-gray-600">
                Showing closest photos within {FOV_ANGLE}° FOV and {mapState.maxDistance.toFixed(1)}km range
            </p>
        </div>
        <button
                on:click={() => (showDebug = !showDebug)}
                class="flex items-center px-2 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 transition-colors"
        >
            {#if showDebug}
                <ChevronDown class="w-4 h-4" />
            {:else}
                <ChevronUp class="w-4 h-4" />
            {/if}
            <span class="ml-1">Debug</span>
        </button>
    </div>

    <!-- Content -->
    <div class="flex flex-1">
        <!-- Gallery "3D" view -->
        <div
                class="flex-1 relative overflow-hidden bg-gray-900 perspective"
                class:border-r.border-gray-200={showDebug}
        >
            <div class="absolute inset-0 flex items-center justify-center">
                {#each visiblePhotos as photo (photo.id)}
                    {#if photo}
                        <!-- Evaluate if we're retrying this photo -->
                        {#let loadingState = loadingStates[photo.id]}
                        {#if loadingState}
                            {#let isRetrying = loadingState.timeout !== null}
                            <div
                                    class="absolute transition-all duration-300"
                                    style="
                      transform:
                        translate({photo.x}%, {photo.y}%)
                        scale({photo.scale});
                      z-index: {photo.z};
                      width: 300px;
                      height: 200px;
                    "
                            >
                                <div class="relative w-full h-full group">
                                    {#if (!photo.loaded || isRetrying)}
                                        <div class="absolute inset-0 rounded-lg loading-background flex items-center justify-center">
                                            {#if isRetrying}
                                                <div class="bg-black bg-opacity-50 rounded-full p-2">
                                                    <RefreshCw class="w-6 h-6 text-white animate-spin" />
                                                </div>
                                            {/if}
                                        </div>
                                    {/if}

                                    <!-- Photo element -->
                                    <img
                                            bind:this={(el) => (imageRefs[photo.id] = el)}
                                            src={photo.thumbnail}
                                            alt=""
                                            class="
                          w-full h-full object-cover rounded-lg shadow-lg
                          transition-opacity duration-300
                          {photo.loaded ? 'opacity-100' : 'opacity-0'}
                        "
                                            style="box-shadow: 0 4px 6px rgba(0,0,0,0.1), 0 1px 3px rgba(0,0,0,0.08);"
                                            on:error={() => {
                          // If below max retries, attempt again
                          if (
                            !loadingStates[photo.id] ||
                            loadingStates[photo.id].attempts < MAX_RETRIES
                          ) {
                            retryLoad(photo);
                          }
                        }}
                                            on:load={() => {
                          // Reset loading state on success
                          setLoadingStates((prev) => ({
                            ...prev,
                            [photo.id]: { attempts: 0, timeout: null }
                          }));
                        }}
                                    />

                                    <!-- Photo info overlay -->
                                    <div
                                            class="
                          absolute bottom-0 left-0 right-0 bg-black bg-opacity-50
                          text-white text-xs p-2 rounded-b-lg
                          opacity-0 group-hover:opacity-100 transition-opacity
                        "
                                    >
                                        <p>{photo.distance?.toFixed(2)}km away</p>
                                        <p>{Math.abs(photo.relativeBearing || 0).toFixed(1)}° from center</p>
                                        <p>Direction diff: {photo.directionDiff?.toFixed(1)}°</p>
                                        {#if loadingState?.attempts > 0}
                                            <p class="text-yellow-300">
                                                Retry attempt: {loadingState.attempts}/{MAX_RETRIES}
                                            </p>
                                        {/if}
                                    </div>
                                </div>
                            </div>
                            {/let}
                        {:else}
                            <!-- If no loadingState entry yet, treat it similarly -->
                            <div
                                    class="absolute transition-all duration-300"
                                    style="
                    transform:
                      translate({photo.x}%, {photo.y}%)
                      scale({photo.scale});
                    z-index: {photo.z};
                    width: 300px;
                    height: 200px;
                  "
                            >
                                <!-- ... same as above or handle gracefully ... -->
                            </div>
                        {/if}
                        {/let}
                    {/if}
                {/each}
            </div>
        </div>

        <!-- Debug sidebar -->
        {#if showDebug}
            <div class="w-64 bg-white overflow-y-auto border-l">
                <div class="p-3 bg-gray-50 border-b sticky top-0">
                    <h3 class="font-medium">Debug Information</h3>
                    {#if downloadError}
                        <div class="mt-2 p-2 bg-red-50 border border-red-200 rounded text-red-700 text-xs flex items-start gap-2">
                            <AlertCircle class="w-4 h-4 flex-shrink-0 mt-0.5" />
                            <p>{downloadError}</p>
                        </div>
                    {/if}
                </div>
                <div class="divide-y">
                    {#each visiblePhotos as photo (photo.id)}
                        <div
                                class="p-3 text-xs hover:bg-gray-50 transition-colors cursor-pointer group"
                                on:click={() => handleDownload(photo)}
                        >
                            <div class="font-medium mb-1 truncate flex items-center justify-between">
                                <span>{photo.file}</span>
                                {#if downloadingPhoto === photo.file}
                                    <div class="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                                {:else}
                                    <Download class="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                                {/if}
                            </div>
                            <div class="space-y-1 text-gray-600">
                                <p>Distance: {photo.distance?.toFixed(2)}km</p>
                                <p>Bearing: {photo.direction.toFixed(1)}°</p>
                                <p>Relative: {photo.relativeBearing?.toFixed(1)}°</p>
                                <p>Direction diff: {photo.directionDiff?.toFixed(1)}°</p>
                                <p>Position: {photo.x?.toFixed(1)}%, {photo.y?.toFixed(1)}%</p>
                                <p>Scale: {photo.scale?.toFixed(2)}</p>
                                <p>Z-Index: {photo.z}</p>
                                {#if loadingStates[photo.id]?.attempts > 0}
                                    <p class="text-yellow-600">
                                        Retries: {loadingStates[photo.id].attempts}/{MAX_RETRIES}
                                    </p>
                                {/if}
                            </div>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}
    </div>
</div>
