<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';

    // Log page changes
    $: {
        if ($page.url.pathname) {
            console.log('Current page:', $page.url.pathname);
        }
    }

    onMount(() => {
        console.log('Layout mounted, initial page:', $page.url.pathname);
    });
</script>

<slot />