<script lang="ts">
    import type { Writable } from 'svelte/store';
    import { autoUploadLicense } from '$lib/data.svelte';
    import PanoramaxShareControl from './PanoramaxShareControl.svelte';
    export let shareStore: Writable<boolean>;
    export let licenseStore: Writable<string | null> = autoUploadLicense;
    export let context = 'Future camera photos. Existing photos keep their choices.';
    export let disabled = false;
    function apply(sharing: boolean, grant?: string) {
        if (grant) licenseStore.set(grant);
        shareStore.set(sharing);
    }
</script>

<PanoramaxShareControl sharing={$shareStore} license={$licenseStore} {context} {disabled} onChange={apply} />
