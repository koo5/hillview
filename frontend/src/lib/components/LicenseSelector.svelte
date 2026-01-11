<script lang="ts">
    import { photoLicense } from '$lib/data.svelte';
    import { CreativeCommons, ExternalLink } from 'lucide-svelte';
    import { openExternalUrl } from '$lib/urlUtils';

    export let disabled = false;
    export let required = false;

    $: isChecked = $photoLicense === 'CC BY-SA 4.0';
    $: isLicenseSet = $photoLicense !== null;

    function handleChange(event: Event) {
        const target = event.target as HTMLInputElement;
        photoLicense.set(target.checked ? 'CC BY-SA 4.0' as const : null);
    }

    async function openLicenseInfo() {
        await openExternalUrl('https://creativecommons.org/licenses/by-sa/4.0/');
    }
</script>


    <label class="checkbox-label">
        <input
            type="checkbox"
            checked={isChecked}
            on:change={handleChange}
            {disabled}
        />

        <div class="label-content">
            <div class="label-text">
                <CreativeCommons size={18} />
                <span>Share as  CC BY-SA 4.0</span>
                <button
                    type="button"
                    class="info-link"
                    on:click={openLicenseInfo}
                    title="Learn more about this license"
                    tabindex={disabled ? -1 : 0}
                >
                    <ExternalLink size={14} />
                </button>
            </div>
			{#if required && !isLicenseSet}
				<div class="requirement-notice">
					Upload is disabled until you select a license for your photos.
				</div>
			{/if}

        </div>
    </label>

<style>

    .checkbox-label {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.75rem;
        border: 1px solid #e5e7eb;
        border-radius: 0.5rem;
        cursor: pointer;
        transition: border-color 0.2s, background-color 0.2s;
    }

    .checkbox-label:hover {
        border-color: #d1d5db;
        background-color: #f9fafb;
    }

    .checkbox-label:has(input:checked) {
        border-color: #3b82f6;
        background-color: #eff6ff;
    }

    input[type="checkbox"] {
        margin-top: 0.125rem;
        flex-shrink: 0;
        cursor: pointer;
    }

    .label-content {
        flex: 1;
        min-width: 0;
    }

    .label-text {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
    }

    .info-link {
        background: none;
        border: none;
        color: #6b7280;
        cursor: pointer;
        padding: 2px;
        border-radius: 4px;
        transition: color 0.2s ease;
        display: flex;
        align-items: center;
    }

    .info-link:hover {
        color: #3b82f6;
    }


    .requirement-notice {
        margin-top: 12px;
        padding: 12px 16px;
        background: #fef2f2;
        border: 1px solid #fecaca;
        border-radius: 8px;
        color: #dc2626;
        font-size: 0.875rem;
        font-weight: 500;
    }

    @media (max-width: 640px) {
        .checkbox-label {
            padding: 12px;
        }

        .label-text {
            flex-wrap: wrap;
            gap: 6px;
        }
    }
</style>
