<script lang="ts">
    import { writable, type Writable } from 'svelte/store';
    import { autoUploadLicense } from '$lib/data.svelte';
    import { canGrantPanoramax } from '$lib/licenses';
    import LicenseChoiceControl from './LicenseChoiceControl.svelte';
    export let licenseStore: Writable<string | null> = autoUploadLicense;
    export let shareStore: Writable<boolean> = writable(false);
    export let disabled = false;
    export let groupName = 'capture-upload-license';
    export let context = 'Future camera photos. Existing photos keep their choices.';
    export let note = 'This does not start an upload.';
    function apply(license: string) {
        licenseStore.set(license);
        if (!canGrantPanoramax(license)) shareStore.set(false);
    }
</script>

<LicenseChoiceControl license={$licenseStore} sharing={$shareStore} {disabled} {groupName} {context} {note} onChange={apply} />
