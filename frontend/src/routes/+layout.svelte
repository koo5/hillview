<script lang="ts">
    import { page } from '$app/stores';
    import { onMount } from 'svelte';
    import { setupDeepLinkListener } from '$lib/authCallback';
    import { TAURI } from '$lib/tauri';
    import ToastContainer from '../components/ToastContainer.svelte';

    // Log page changes
    $: {
        if ($page.url.pathname) {
            //console.log('🢄Current page:', $page.url.pathname);
        }
    }

    onMount(async () => {
        //console.log('🢄Layout mounted, initial page:', $page.url.pathname);
        
        // Set up deep link listener for authentication callbacks (only in Tauri)
        if (TAURI) {
            await setupDeepLinkListener();
        }
    });
</script>

<slot />
<ToastContainer />