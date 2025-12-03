<script lang="ts">
    import { Compass, Car, PersonStanding, ChevronDown } from 'lucide-svelte';
    import { compassState, compassEnabled, compassAvailable, enableCompass, disableCompass, compassError } from '$lib/compass.svelte';
    import { bearingMode, type BearingMode } from '$lib/mapState';
    import { createEventDispatcher } from 'svelte';

    const dispatch = createEventDispatcher<{
        modeChange: { mode: BearingMode };
        toggleTracking: { enabled: boolean };
    }>();

    // Dropdown state
    let dropdownOpen = false;
    let longPressTimer: number | null = null;
    let longPressStarted = false;
    let buttonElement: HTMLButtonElement;

    // Long press detection for mobile
    const LONG_PRESS_DURATION = 500; // ms

    function handlePointerDown(event: PointerEvent) {
        event.preventDefault();
        longPressStarted = false;

        longPressTimer = window.setTimeout(() => {
            longPressStarted = true;
            dropdownOpen = true;
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
        // On desktop, clicking the dropdown arrow opens the dropdown
        // Clicking the main button toggles tracking
        const target = event.target as HTMLElement;
        const isDropdownTrigger = target.closest('.dropdown-trigger');

        if (isDropdownTrigger) {
            event.stopPropagation();
            dropdownOpen = !dropdownOpen;
        } else if (!dropdownOpen) {
            toggleTracking();
        }
    }

    function toggleTracking() {
        if ($compassEnabled) {
            disableCompass();
            dispatch('toggleTracking', { enabled: false });
        } else {
            enableCompass();
            dispatch('toggleTracking', { enabled: true });
        }
    }

    function selectMode(mode: BearingMode) {
        bearingMode.set(mode);
        dropdownOpen = false;

        // If compass is currently off, enable it when selecting a mode
        if (!$compassEnabled) {
            enableCompass();
            dispatch('toggleTracking', { enabled: true });
        }

        dispatch('modeChange', { mode });
    }

    // Close dropdown when clicking outside
    function handleDocumentClick(event: MouseEvent) {
        if (dropdownOpen && buttonElement && !buttonElement.contains(event.target as Node)) {
            dropdownOpen = false;
        }
    }

    // Browser detection for showing dropdown indicator
    $: isTouch = typeof window !== 'undefined' && ('ontouchstart' in window || navigator.maxTouchPoints > 0);

    $: buttonClass = [
        'compass-button',
        $compassState === 'active' ? 'active' : '',
        $compassState === 'starting' ? 'loading' : '',
        $compassState === 'error' ? 'error' : '',
        $bearingMode === 'car' ? 'car-mode' : 'walking-mode',
        dropdownOpen ? 'dropdown-open' : ''
    ].filter(Boolean).join(' ');

    $: tooltipText = `Auto bearing updates (${$bearingMode === 'car' ? 'GPS' : 'compass'} mode)${$compassError ? ' - Error: ' + $compassError : ''}${!isTouch ? ' • Click arrow for mode options' : ' • Long press for mode options'}`;
</script>

<svelte:document on:click={handleDocumentClick} />

<div class="compass-button-container" bind:this={buttonElement}>
    <button
        class={buttonClass}
        on:pointerdown={handlePointerDown}
        on:pointerup={handlePointerUp}
        on:pointerleave={handlePointerLeave}
        on:click={handleClick}
        title={tooltipText}
        disabled={$bearingMode === 'walking' && !$compassAvailable}
        data-testid="compass-button"
    >
        <div class="button-content">
            <Compass />
            <div class="mode-indicator">
                {#if $bearingMode === 'car'}
                    <Car size={12} />
                {:else}
                    <PersonStanding size={12} />
                {/if}
            </div>
            {#if !isTouch}
                <div class="dropdown-trigger">
                    <ChevronDown size={14} />
                </div>
            {/if}
        </div>
    </button>

    {#if dropdownOpen}
        <div class="dropdown-menu" data-testid="compass-dropdown">
            <button
                class="dropdown-item {$bearingMode === 'walking' ? 'selected' : ''}"
                on:click={() => selectMode('walking')}
                data-testid="walking-mode-option"
            >
                <PersonStanding size={16} />
                <span>Walking Mode</span>
                <small>Compass bearing</small>
            </button>
            <button
                class="dropdown-item {$bearingMode === 'car' ? 'selected' : ''}"
                on:click={() => selectMode('car')}
                data-testid="car-mode-option"
            >
                <Car size={16} />
                <span>Car Mode</span>
                <small>GPS bearing</small>
            </button>
        </div>
    {/if}
</div>

<style>
    .compass-button-container {
        position: relative;
        display: inline-block;
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
        min-width: 50px;
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

    .compass-button.active.car-mode {
        background-color: #ff5722;
        border-color: #ff5722;
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
        gap: 2px;
        position: relative;
    }

    .mode-indicator {
        position: absolute;
        bottom: -2px;
        right: -2px;
        background: rgba(255, 255, 255, 0.9);
        border-radius: 50%;
        padding: 1px;
        line-height: 1;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }

    .compass-button.active .mode-indicator {
        background: rgba(255, 255, 255, 0.9);
        color: #333;
    }

    .dropdown-trigger {
        margin-left: 2px;
        opacity: 0.7;
        display: flex;
        align-items: center;
    }

    .dropdown-menu {
        position: absolute;
        top: 100%;
        right: 0;
        background: white;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        min-width: 160px;
        z-index: 1000;
        overflow: hidden;
        margin-top: 2px;
    }

    .dropdown-item {
        width: 100%;
        padding: 12px;
        border: none;
        background: white;
        cursor: pointer;
        text-align: left;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: background-color 0.2s ease;
        flex-direction: column;
        align-items: flex-start;
    }

    .dropdown-item:hover {
        background-color: #f5f5f5;
    }

    .dropdown-item.selected {
        background-color: #e3f2fd;
    }

    .dropdown-item span {
        font-weight: 500;
        color: #333;
        margin-left: 24px;
        margin-top: -16px;
    }

    .dropdown-item small {
        font-size: 0.8em;
        color: #666;
        margin-left: 24px;
        margin-top: -4px;
    }

    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.6; }
        100% { opacity: 1; }
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
        .compass-button {
            min-width: 48px;
            min-height: 48px;
            touch-action: manipulation;
        }

        .dropdown-trigger {
            display: none;
        }
    }
</style>