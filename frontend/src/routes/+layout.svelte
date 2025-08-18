<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';
    import { setupDeepLinkListener } from '$lib/authCallback';

    // Log page changes
    $: {
        if ($page.url.pathname) {
            console.log('Current page:', $page.url.pathname);
        }
    }

    onMount(async () => {
        console.log('Layout mounted, initial page:', $page.url.pathname);
        
        // Set up deep link listener for authentication callbacks
        await setupDeepLinkListener();
    });
</script>

<slot />