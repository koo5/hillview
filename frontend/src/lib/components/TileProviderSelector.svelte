<script lang="ts">
    import { Map as MapIcon, ChevronUp, ChevronDown } from 'lucide-svelte';
    import { getAvailableProviders, setTileProvider, currentTileProvider } from '$lib/tileProviders';
    import type { ProviderName } from '$lib/tileProviders';
    import {
        showDropdownMenu,
        closeDropdownMenu,
        dropdownMenuState,
        type DropdownMenuItem
    } from '$lib/components/dropdown-menu/dropdownMenu.svelte';

    const MENU_TEST_ID = 'tile-provider-menu';
    let buttonElement: HTMLButtonElement;

    $: isOpen = $dropdownMenuState.visible && $dropdownMenuState.testId === MENU_TEST_ID;

    function buildItems(current: ProviderName): DropdownMenuItem[] {
        return [
            { type: 'header', label: 'Map provider' },
            ...getAvailableProviders().map(provider => ({
                id: provider.key,
                label: provider.name,
                selected: provider.key === current,
                testId: `tile-provider-option-${provider.key}`,
                onclick: () => setTileProvider(provider.key)
            }))
        ];
    }

    function toggleMenu() {
        if (isOpen) {
            closeDropdownMenu();
            return;
        }
        showDropdownMenu(buildItems($currentTileProvider), buttonElement, {
            placement: 'above-right',
            testId: MENU_TEST_ID
        });
    }
</script>

<button
    bind:this={buttonElement}
    class="provider-button"
    on:click={toggleMenu}
    title="Select map tile provider"
    data-testid="tile-provider-button"
>
    <MapIcon size={16} />
    {#if isOpen}
        <ChevronDown size={12} />
    {:else}
        <ChevronUp size={12} />
    {/if}
</button>

<style>
    .provider-button {
        display: flex;
        align-items: center;
        padding: 0.6rem 0.3rem;
        background-color: rgba(255, 255, 255, 0.6);
        border: 1px solid #ccc;
        border-radius: 0.25rem;
        cursor: pointer;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        transition: all 0.2s;
        font-size: 0.75rem;
        -webkit-user-select: none;
        user-select: none;
    }

    .provider-button :global(svg) {
        pointer-events: none; /* Prevent SVG icons from intercepting clicks */
    }

    .provider-button:hover {
        background-color: #f0f0f0;
    }
</style>
