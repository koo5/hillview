<script lang="ts">
    import { createEventDispatcher } from 'svelte';
    import Spinner from './Spinner.svelte';

    /** While true, a centered spinner is shown instead of the slotted content. */
    export let loading = false;
    /** While true (and not loading), the error state is shown — by default a retry. */
    export let error = false;
    /** Forwarded to <Spinner>. */
    export let color = '#ffffff';

    const dispatch = createEventDispatcher<{ retry: void }>();
</script>

{#if loading}
    <div class="loadable-spinner" data-testid="loadable-spinner">
        <Spinner {color} />
    </div>
{:else if error}
    <slot name="error">
        <div class="loadable-error" data-testid="loadable-error">
            <p>
                Couldn't load.
                <button type="button" class="loadable-retry" on:click={() => dispatch('retry')}>
                    Retry
                </button>
            </p>
        </div>
    </slot>
{:else}
    <slot />
{/if}

<style>
    .loadable-spinner,
    .loadable-error {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1rem;
    }
    .loadable-retry {
        background: none;
        border: none;
        color: inherit;
        text-decoration: underline;
        cursor: pointer;
        padding: 0;
        font: inherit;
    }
</style>
