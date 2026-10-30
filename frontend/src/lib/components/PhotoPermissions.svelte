<script lang="ts">
	import type { Writable } from 'svelte/store';
	import { autoUploadLicense, capturePanoramaxShare } from '$lib/data.svelte';
	import LicenseSelector from './LicenseSelector.svelte';
	import PanoramaxSharing from './PanoramaxSharing.svelte';
	import ContributionSummary from './ContributionSummary.svelte';
	export let licenseStore: Writable<string | null> = autoUploadLicense;
	export let shareStore: Writable<boolean> = capturePanoramaxShare;
	export let heading = 'Photo permissions';
	export let context = 'Future camera photos. Existing photos keep their choices.';
	export let groupName = 'capture-upload-license';
</script>

<section class="permissions" data-testid="photo-permissions-settings">
	<h2>{heading}</h2>
	<p class="context">{context}</p>
	<div class="card">
		<LicenseSelector {licenseStore} {shareStore} {context} {groupName} />
		<div class="sharing-row"><PanoramaxSharing {licenseStore} {shareStore} {context} /></div>
		<ContributionSummary license={$licenseStore} sharing={$shareStore} compact={true} showLogin={false} />
		<a href="/settings/panoramax" data-testid="panoramax-info-link">How licenses and Panoramax sharing work</a>
	</div>
</section>

<style>
	.permissions { margin-bottom: 1.75rem; color: #1f2937; font: 1rem/1.5 system-ui, sans-serif; }
	h2 { font-size: 1.25rem; margin: 0 0 .35rem; }
	.context { margin: 0 0 .75rem; color: #475569; }
	.card { padding: 1rem; border: 1px solid #cbd5e1; border-radius: .75rem; background: white; }
	.sharing-row { border-top: 1px solid #e2e8f0; margin-top: 1rem; padding-top: .5rem; }
	a { color: #1d4ed8; text-decoration: underline; display: inline-flex; align-items: center; min-height: 44px; }
</style>
