<script lang="ts">
    import StandardHeader from './StandardHeader.svelte';
    import NavigationMenu from './NavigationMenu.svelte';

    import type { Alert } from '$lib/alertSystem.svelte';

    export let title: string;
    export let showBackButton: boolean = true;
    export let showMenuButton: boolean = true;
    export let fallbackHref: string = '/';
    export let useSmartBack: boolean = true;
    export let alertMessage: string = '';
    export let alertType: Alert['type'] = 'info';

    let menuOpen = false;

    function toggleMenu() {
        menuOpen = !menuOpen;
    }

    function closeMenu() {
        menuOpen = false;
    }
</script>

<div class="header-with-alert">
    <StandardHeader
        {title}
        {showBackButton}
        {showMenuButton}
        onMenuClick={toggleMenu}
        {fallbackHref}
        {useSmartBack}
    >
        <slot name="actions" slot="actions" />
    </StandardHeader>
    <NavigationMenu isOpen={menuOpen} onClose={closeMenu} />

    {#if alertMessage}
        <div class="alert alert-{alertType}">
            {alertMessage}
        </div>
    {/if}
</div>

<style>
    .header-with-alert {
        position: relative;
    }

    .alert {
        padding: 0.75rem 1rem;
        border-radius: 0.375rem;
        margin: 0.5rem 1rem;
        font-size: 0.875rem;
        border: 1px solid;
    }

    .alert-info {
        background-color: #dbeafe;
        border-color: #93c5fd;
        color: #1e40af;
    }

    .alert-success {
        background-color: #dcfce7;
        border-color: #86efac;
        color: #166534;
    }

    .alert-warning {
        background-color: #fef3c7;
        border-color: #fcd34d;
        color: #92400e;
    }

    .alert-error {
        background-color: #fecaca;
        border-color: #f87171;
        color: #991b1b;
    }
</style>
