<script lang="ts">
    import { Map as MapIcon, ChevronUp, ChevronDown } from 'lucide-svelte';
    import { getAvailableProviders, setTileProvider, currentTileProvider, getProviderDisplayName } from '$lib/tileProviders';
    import type { ProviderName } from '$lib/tileProviders';

    let showMenu = false;
    let availableProviders = getAvailableProviders();

    function selectProvider(providerKey: ProviderName) {
        setTileProvider(providerKey);
        showMenu = false;
    }

    function toggleMenu() {
        showMenu = !showMenu;
    }

    // Close menu when clicking outside
    function handleClickOutside(event: MouseEvent) {
        const target = event.target as Element;
        if (!target?.closest?.('.provider-selector')) {
            showMenu = false;
        }
    }
</script>

<svelte:window on:click={handleClickOutside} />

<div class="provider-selector">
    <button
        class="provider-button"
        on:click={toggleMenu}
        title="Select map tile provider"
    >
        <MapIcon size={16} />
        {#if showMenu}
            <ChevronDown size={12} />
        {:else}
            <ChevronUp size={12} />
        {/if}
    </button>

    {#if showMenu}
        <div class="provider-menu">
            <div class="provider-menu-header">Map Style</div>
            {#each availableProviders as provider}
                <button
                    class="provider-option {provider.key === $currentTileProvider ? 'active' : ''}"
                    on:click={() => selectProvider(provider.key)}
                >
                    {provider.name}
                </button>
            {/each}
        </div>
    {/if}
</div>

<style>
    .provider-selector {
        position: relative;
        z-index: 1000;
    }

    .provider-button {
		position: absolute;
		bottom: 4rem;
        display: flex;
        align-items: center;
        gap: 0.25rem;
        padding: 0.5rem;
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        cursor: pointer;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        transition: all 0.2s;
        font-size: 0.75rem;
    }

    .provider-button :global(svg) {
        pointer-events: none; /* Prevent SVG icons from intercepting clicks */
    }

    .provider-button:hover {
        background-color: #f0f0f0;
    }

    .provider-menu {
        position: absolute;
        bottom: 4rem;
        left: 0;
        margin-bottom: 0.25rem;
        background-color: white;
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        min-width: 200px;
        max-height: 300px;
        overflow-y: auto;
    }

    .provider-menu-header {
        padding: 0.5rem;
        font-weight: bold;
        font-size: 0.75rem;
        border-bottom: 1px solid #eee;
        background-color: #f8f8f8;
        color: #666;
    }

    .provider-option {
        display: block;
        width: 100%;
        padding: 0.5rem;
        text-align: left;
        background: none;
        border: none;
        cursor: pointer;
        transition: background-color 0.2s;
        font-size: 0.75rem;
        border-bottom: 1px solid #f0f0f0;
    }

    .provider-option:hover {
        background-color: #f0f0f0;
    }

    .provider-option.active {
        background-color: #4285F4;
        color: white;
    }

    .provider-option:last-child {
        border-bottom: none;
    }
</style>
