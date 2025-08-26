<script lang="ts">
    import { onMount } from 'svelte';
    import { setupDeepLinkListener } from '$lib/authCallback';
    import { TAURI } from '$lib/tauri';
    import ToastContainer from '../components/ToastContainer.svelte';

    onMount(async () => {
        if (TAURI) {
            await setupDeepLinkListener();
        }
    });
</script>

<slot />
<ToastContainer />