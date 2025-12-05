<script lang="ts">
    import { Car, PersonStanding } from 'lucide-svelte';
    import { bearingMode, type BearingMode } from '$lib/mapState';
    import { createEventDispatcher } from 'svelte';

    const dispatch = createEventDispatcher<{
        selectMode: { mode: BearingMode };
        close: {};
    }>();

    export let visible = false;
    export let position = { top: 0, right: 0 };

    function selectMode(mode: BearingMode) {
        dispatch('selectMode', { mode });
    }

    let menuElement: HTMLElement;

    function handleDocumentClick(event: MouseEvent) {
        if (visible && menuElement && !menuElement.contains(event.target as Node)) {
            dispatch('close');
        }
    }
</script>

<svelte:document on:pointerup={handleDocumentClick} />

{#if visible}
    <div
        class="compass-mode-menu-portal"
        style="top: {position.top}px; right: {position.right}px;"
        data-testid="compass-mode-menu"
        bind:this={menuElement}
    >
        <div class="compass-mode-menu">
            <button
                class="menu-item {$bearingMode === 'walking' ? 'selected' : ''}"
                on:click={() => selectMode('walking')}
                data-testid="walking-mode-option"
            >
                <PersonStanding size={16} />
                <span>Walking Mode</span>
                <small>Compass bearing</small>
            </button>
            <button
                class="menu-item {$bearingMode === 'car' ? 'selected' : ''}"
                on:click={() => selectMode('car')}
                data-testid="car-mode-option"
            >
                <Car size={16} />
                <span>Car Mode</span>
                <small>GPS bearing</small>
            </button>
        </div>
    </div>
{/if}

<style>
    .compass-mode-menu-portal {
        position: fixed !important;
        z-index: 2147483647 !important;
        pointer-events: auto !important;
    }

    .compass-mode-menu {
        position: relative;
        background: white;
        border: 1px solid #ddd;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        min-width: 160px;
        overflow: hidden;
        margin-top: 2px;
    }

    .menu-item {
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

    .menu-item:hover {
        background-color: #f5f5f5;
    }

    .menu-item.selected {
        background-color: #e3f2fd;
    }

    .menu-item span {
        font-weight: 500;
        color: #333;
        margin-left: 24px;
        margin-top: -16px;
    }

    .menu-item small {
        font-size: 0.8em;
        color: #666;
        margin-left: 24px;
        margin-top: -4px;
    }
</style>