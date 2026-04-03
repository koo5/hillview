<script lang="ts">
    import { compassState, compassEnabled, compassAvailable, compassError } from '$lib/compass.svelte';
    import { gpsOrientationInternalState, gpsOrientationEnabled, gpsOrientationError, gpsOrientationFlash } from '$lib/gpsOrientation.svelte';
    import { bearingMode, type BearingMode } from '$lib/mapState';
    import { enableBearingTracking, disableBearingTracking, selectBearingMode } from '$lib/bearingTracking';
	import CompassButtonInner from "$lib/components/CompassButtonInner.svelte";
    import CompassModeMenu from '$lib/components/CompassModeMenu.svelte';

    const doLog = false;

    // Menu state
    let menuOpen = false;
    let menuPosition = { top: 0, right: 0 };
    let longPressTimer: number | null = null;
    let longPressStarted = false;
    let longPressArmed = false;
    let buttonElement: HTMLButtonElement;
    let pointerHandled = false;

    // Long press detection for mobile
    const LONG_PRESS_DURATION = 500; // ms

    function shouldStartLongPress(event: PointerEvent) {
        if (event.button !== 0) {
            return false;
        }

        const target = event.target as HTMLElement | null;
        return !target?.closest('.dropdown-trigger');
    }

    function showMenu() {
        const rect = buttonElement.getBoundingClientRect();
        menuPosition = {
            top: rect.bottom + 2,
            right: window.innerWidth - rect.right
        };
        menuOpen = true;
    }

    function hideMenu() {
        menuOpen = false;
    }

    function handlePointerDown(event: PointerEvent) {
        pointerHandled = false;
        longPressStarted = false;
        longPressArmed = shouldStartLongPress(event);

        if (!longPressArmed) {
            return;
        }

        if (event.pointerType !== 'mouse') {
            event.preventDefault();
        }

        longPressTimer = window.setTimeout(() => {
            longPressStarted = true;
            showMenu();
        }, LONG_PRESS_DURATION);
    }

    function handlePointerUp(event: PointerEvent) {
        if (!longPressArmed) {
            return;
        }

        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }

        if (longPressStarted) {
            // Long press completed - prevent event from bubbling to document
            event.stopPropagation();
            pointerHandled = true;
        } else if (event.pointerType === 'mouse') {
            longPressArmed = false;
            return;
        } else if (menuOpen) {
            hideMenu();
            pointerHandled = true;
        } else {
            // Short tap - toggle tracking
            toggleTracking();
            pointerHandled = true;
        }

        longPressStarted = false;
        longPressArmed = false;
    }

    function handlePointerLeave(event: PointerEvent) {
        if (!longPressArmed) {
            return;
        }

        if (longPressTimer) {
            clearTimeout(longPressTimer);
            longPressTimer = null;
        }
        longPressStarted = false;
        longPressArmed = false;
    }

    // For desktop browsers - show dropdown arrow and handle clicks
    function handleClick(event: MouseEvent) {
        // Skip click if we already handled it with pointer events
        if (pointerHandled) {
            pointerHandled = false;
            return;
        }

        // On desktop, clicking the dropdown arrow opens the dropdown.
        // Clicking the main button closes an open menu, otherwise toggles tracking.
        const target = event.target as HTMLElement;
        const isDropdownTrigger = target.closest('.dropdown-trigger');

        if (menuOpen) {
            if (isDropdownTrigger) {
                event.stopPropagation();
            }
            hideMenu();
            return;
        }

        if (isDropdownTrigger) {
            event.stopPropagation();
            showMenu();
        } else {
            if (doLog) console.log('🔘 click: Calling toggleTracking()');
            toggleTracking();
        }
    }

    function toggleTracking() {
        const isAnyTrackingEnabled = $compassEnabled || $gpsOrientationEnabled;

        if (isAnyTrackingEnabled) {
            disableBearingTracking();
        } else {
            enableBearingTracking();
        }
    }

    function handleMenuSelect(event: CustomEvent<{ mode: BearingMode }>) {
        selectBearingMode(event.detail.mode);
        hideMenu();
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

<div class="compass-button-container">
    <button
        bind:this={buttonElement}
        class="{buttonClass}{$gpsOrientationFlash ? ' flash' : ''}"
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

    <CompassModeMenu
        visible={menuOpen}
        position={menuPosition}
        anchorElement={buttonElement}
        on:selectMode={handleMenuSelect}
        on:close={hideMenu}
    />
</div>

<style>
    .compass-button-container {
        position: relative;
        display: inline-block;
        /* Remove z-index to avoid creating stacking context */
    }

    .compass-button {
        background-color: rgba(255, 255, 255, 0.7);
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

    .compass-button.flash {
        border-radius: 100%;
    }

    .compass-button.dropdown-open {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
    }

    .compass-button.dropdown-open:not(.active):not(.error) {
        background-color: rgba(255, 255, 255, 1);
    }

    .compass-button.dropdown-open.active,
    .compass-button.dropdown-open.error {
        color: white;
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
