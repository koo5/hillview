<script lang="ts">
    import { Menu, ArrowLeft } from 'lucide-svelte';
    import { goBack, canNavigateBack, getPreviousPath } from '$lib/navigation.svelte';
    import { goto } from '$app/navigation';
    import AlertArea from './AlertArea.svelte';

    export let title: string;
    export let showBackButton: boolean = true;
    export let showMenuButton: boolean = true;
    export let onMenuClick: (() => void) | null = null;
    export let fallbackHref: string = '/';
    export let useSmartBack: boolean = true;

    function handleBackClick() {
        if (useSmartBack && canNavigateBack()) {
            goBack(fallbackHref);
        } else {
            goto(fallbackHref);
        }
    }

    function handleMenuClick() {
        if (onMenuClick) {
            onMenuClick();
        }
    }

    // For accessibility and SEO, provide a meaningful href
    $: smartHref = useSmartBack ? getPreviousPath(fallbackHref) : fallbackHref;
</script>

<header class="standard-header">
    <div class="header-left">
        {#if showMenuButton}
            <button
                class="header-button menu-button"
                on:click={handleMenuClick}
                aria-label="Toggle menu"
                data-testid="header-menu-button"
            >
                <Menu size={24} />
            </button>
        {/if}

        {#if showBackButton}
            <button
                class="header-button back-button"
                on:click={handleBackClick}
                aria-label="Go back"
                data-testid="header-back-button"
                data-href={smartHref}
            >
                <ArrowLeft size={24} />
            </button>
        {/if}
    </div>

    <div class="header-center">
        <h1 class="header-title">{title}</h1>
    </div>

    <div class="header-right">
        <slot name="actions" />
    </div>
</header>
<AlertArea position="header" />

<style>
    .standard-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0px 16px;
        background: white;
        border-bottom: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 30001;
        min-height: 50px;
    }

    .header-left,
    .header-right {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 0 0 auto;
        min-width: 40px; /* Ensure space for buttons */
    }

    .header-center {
        flex: 1;
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 0 16px;
        overflow: hidden;
    }

    .header-title {
        font-size: 1.25rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .header-button {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 40px;
        height: 40px;
        padding: 0;
        background: white;
        color: #374151;
        border: none;
        border-radius: 50%;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    .header-button:hover {
        transform: scale(1.05);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.25);
    }

    .header-button:active {
        transform: scale(0.95);
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
    }

    /* Responsive adjustments */
    @media (max-width: 640px) {
        .standard-header {
            padding: 8px 12px;
            min-height: 56px;
        }

        .header-title {
            font-size: 1.125rem;
        }

        .header-center {
            padding: 0 8px;
        }
    }
</style>
