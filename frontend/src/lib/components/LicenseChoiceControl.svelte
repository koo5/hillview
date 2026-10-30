<script lang="ts">
    import { UPLOAD_LICENSES } from '$lib/licenses';
    import LicenseDialog from './LicenseDialog.svelte';
    export let license: string | null = null;
    export let sharing = false;
    export let disabled = false;
    export let groupName = 'capture-upload-license';
    export let context = 'Future camera photos. Existing photos keep their choices.';
    export let note = 'This does not start an upload.';
    export let testId = 'license-change-button';
    export let currentTestId = 'license-current';
    export let onChange: (license: string) => void | Promise<void>;
    let choosing = false;
    $: option = UPLOAD_LICENSES.find(option => option.id === license);
</script>

<div class="license-summary" data-license-group={groupName} data-testid="license-summary">
    <div><span class="caption">License to Hillview</span>
        <strong data-testid={currentTestId}>{option?.label ?? 'Not chosen'}</strong>
        {#if !license}<span data-testid="license-unset">Choose before uploading.</span>{/if}
    </div>
    <button type="button" on:click={() => choosing = true} {disabled} data-testid={testId}
        aria-label={`${license ? 'Change' : 'Choose'} upload license. ${context}`}>
        {license ? 'Change' : 'Choose a license'}
    </button>
</div>
{#if choosing}
    <LicenseDialog current={license} sharing={sharing} {context} {note}
        onConfirm={onChange} onClose={() => choosing = false} />
{/if}

<style>
    .license-summary { display: flex; align-items: center; justify-content: space-between; gap: 1rem; font: 1rem/1.5 system-ui, sans-serif; }
    .license-summary > div { display: flex; flex-direction: column; gap: .2rem; }
    .caption { color: #475569; }
    strong { color: #1f2937; }
    button { min-height: 44px; flex-shrink: 0; padding: .5rem .8rem; border: 1px solid #94a3b8; border-radius: .5rem; background: white; color: #1d4ed8; font: inherit; cursor: pointer; }
    button:disabled { opacity: .55; cursor: default; }
    @media(max-width: 420px) { .license-summary { align-items: flex-start; flex-wrap: wrap; gap: .5rem; } }
</style>
