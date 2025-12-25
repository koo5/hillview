<script lang="ts">
    import { Compass, Disc, Car, PersonStanding, ChevronDown } from 'lucide-svelte';
    import { compassState, compassEnabled, compassAvailable, enableCompass, disableCompass, compassError } from '$lib/compass.svelte';
    import { gpsOrientationInternalState, gpsOrientationEnabled, enableGpsOrientation, disableGpsOrientation, gpsOrientationError } from '$lib/gpsOrientation.svelte';
    import { bearingMode, type BearingMode } from '$lib/mapState';
    import { createEventDispatcher } from 'svelte';
	import CompassButtonInner from "$lib/components/CompassButtonInner.svelte";

    const dispatch = createEventDispatcher<{
        showMenu: { buttonRect: DOMRect };
        hideMenu: {};
    }>();



    // Menu state
    let menuOpen = false;
    let longPressTimer: number | null = null;
    let longPressStarted = false;
    let buttonElement: HTMLDivElement;
    let pointerHandled = false;

    // Long press detection for mobile
    const LONG_PRESS_DURATION = 500; // ms

    function showMenu() {
        menuOpen = true;
        const rect = buttonElement.getBoundingClientRect();
        dispatch('showMenu', { buttonRect: rect });
    }

    function hideMenu() {
        menuOpen = false;
        dispatch('hideMenu', {});
    }

    function handlePointerDown(event: PointerEvent) {
        event.preventDefault();
        longPressStarted = false;
        pointerHandled = false;

        longPressTimer = window.setTimeout(() => {
            longPressStarted = true;
            showMenu();
        }, LONG_PRESS_DURATION);
    }

    function handlePointerUp(event: PointerEvent) {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        if (!longPressStarted) {
            // Short click - toggle tracking
            toggleTracking();
            pointerHandled = true;
        } else {
            // Long press completed - prevent event from bubbling to document
            event.stopPropagation();
            pointerHandled = true;
        }

        longPressStarted = false;
    }

    function handlePointerLeave(event: PointerEvent) {
        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        longPressStarted = false;
    }

    // For desktop browsers - show dropdown arrow and handle clicks
    function handleClick(event: MouseEvent) {
        // Skip click if we already handled it with pointer events
        if (pointerHandled) {
            pointerHandled = false;
            return;
        }

        // On desktop, clicking the dropdown arrow opens the dropdown
        // Clicking the main button toggles tracking
        const target = event.target as HTMLElement;
        const isDropdownTrigger = target.closest('.dropdown-trigger');

        if (isDropdownTrigger) {
            event.stopPropagation();
            if (menuOpen) {
                hideMenu();
            } else {
                showMenu();
            }
        } else if (!menuOpen) {
            console.log('🔘 click: Calling toggleTracking()');
            toggleTracking();
        }
    }

    function toggleTracking() {
        const isAnyTrackingEnabled = $compassEnabled || $gpsOrientationEnabled;

        if (isAnyTrackingEnabled) {
            console.log('toggleTracking: Disabling orientation tracking');
            disableCompass();
            disableGpsOrientation();
        } else {
            // Enable the system based on current bearing mode
            if ($bearingMode === 'walking') {
                console.log('toggleTracking: Enabling compass (walking mode)');
                enableCompass();
            } else {
                console.log('toggleTracking: Enabling GPS orientation (car mode)');
                enableGpsOrientation();
            }
        }
    }

    export function selectMode(mode: BearingMode) {
        const wasAnyTrackingEnabled = $compassEnabled || $gpsOrientationEnabled;

        bearingMode.set(mode);
        hideMenu();

        if (wasAnyTrackingEnabled) {
            // Switch tracking system while maintaining enabled state
            if (mode === 'walking') {
                disableGpsOrientation();
                enableCompass();
            } else {
                disableCompass();
                enableGpsOrientation();
            }
        } else {
            // If tracking was off, enable it for the selected mode
            if (mode === 'walking') {
                disableGpsOrientation();
                enableCompass();
            } else {
                disableCompass();
                enableGpsOrientation();
            }
        }
    }


    // Browser detection for showing dropdown indicator
    $: isTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);

    // Combined state logic for display
    // Button state primarily reflects user preference
    $: userWantsTracking = ($bearingMode === 'walking' && $compassEnabled) ||
                          ($bearingMode === 'car' && $gpsOrientationEnabled);

    // Technical state for visual feedback
    $: isTrackingStarting = ($bearingMode === 'walking' && $compassState === 'starting') ||
                           ($bearingMode === 'car' && $gpsOrientationInternalState === 'starting');

    $: isTrackingError = ($bearingMode === 'walking' && $compassState === 'error') ||
                        ($bearingMode === 'car' && $gpsOrientationInternalState === 'error');

    $: currentError = $bearingMode === 'walking' ? $compassError : $gpsOrientationError;

    $: isButtonDisabled = $bearingMode === 'walking' && !$compassAvailable;

    $: buttonClass = [
        'compass-button',
        userWantsTracking ? 'active' : '',
        isTrackingStarting ? 'loading' : '',
        isTrackingError ? 'error' : '',
        $bearingMode === 'car' ? 'car-mode' : 'walking-mode',
        menuOpen ? 'dropdown-open' : ''
    ].filter(Boolean).join(' ');

    $: tooltipText = `Auto bearing updates (${$bearingMode === 'car' ? 'GPS' : 'compass'} mode)${currentError ? ' - Error: ' + currentError : ''}${!isTouch ? ' • Click arrow for mode options' : ' • Long press for mode options'}`;
</script>

<div class="compass-button-container" bind:this={buttonElement}>
    <button
        class={buttonClass}
        on:pointerdown={handlePointerDown}
        on:pointerup={handlePointerUp}
        on:pointerleave={handlePointerLeave}
        on:click={handleClick}
        title={tooltipText}
        disabled={isButtonDisabled}
        data-testid="compass-button"
    >
        <CompassButtonInner bearingMode={$bearingMode} />



    </button>

</div>

<style>
    .compass-button-container {
        position: relative;
        display: inline-block;
        /* Remove z-index to avoid creating stacking context */
    }

    .compass-button {
        background-color: rgba(255, 255, 255, 0.9);
        border: 2px solid #ddd;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
        transition: all 0.2s ease;
        position: relative;
        min-width: 60px;
        min-height: 44px;
        display: flex;
        align-items: center;
        justify-content: center;
        -webkit-user-select: none;
        user-select: none;
    }

    .compass-button:hover {
        background-color: rgba(255, 255, 255, 1);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .compass-button:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }

    .compass-button.active {
        background-color: #4285F4;
        border-color: #4285F4;
        color: white;
    }

    .compass-button.loading {
        animation: pulse 1.5s ease-in-out infinite;
    }

    .compass-button.error {
        background-color: #f44336;
        border-color: #f44336;
        color: white;
    }

    .compass-button.dropdown-open {
        background-color: rgba(255, 255, 255, 1);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .button-content {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 4px;
        position: relative;
    }

    .mode-section {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1px;
    }

    .mode-indicator {
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .dropdown-trigger {
        opacity: 0.7;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .long-press-indicator {
        opacity: 0.6;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
    }


    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
        .compass-button {
            /*min-width: 48px;*/
            /*min-height: 48px;*/
            touch-action: manipulation;
        }

        /*.dropdown-trigger {*/
        /*    display: none;*/
        /*}*/
    }
</style>
