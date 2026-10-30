<script lang="ts">
	import { auth } from '$lib/authStore';
	import { publishedLicense } from '$lib/licenses';
	import { licenseLabelFor } from '$lib/photoUtils';
	export let license: string | null = null;
	export let sharing = false;
	export let showLogin = true;
	export let compact = false;
	$: published = publishedLicense(license, sharing);
</script>

<div class="summary" data-testid="contribution-summary" aria-live="polite">
	{#if !license}
		<p>{compact ? 'No photos can upload until you choose a license.' : 'Choose an upload license before uploading. You can set your sharing preference now; it does not choose a license or start an upload.'}</p>
	{:else}
		<p data-testid="contribution-published-license"><strong>Published as:</strong> {licenseLabelFor(published)}.</p>
		{#if license === 'ccbysa4+osm'}
			<p>{compact ? 'CC does not permit Panoramax contribution.' : 'This grant alone does not permit Panoramax federation. A compatible grant is required to offer photos.'}</p>
		{:else if sharing}
			<p>{compact ? 'Eligible views will be offered to Panoramax.' : 'Sharing offers eligible photos to Panoramax. Approval, anonymization checks and selection of representative views still apply; not every offered photo is included.'}</p>
		{:else}
			<p>{compact ? 'Panoramax contribution is off.' : 'These photos are not offered to the Panoramax federation.'} {!compact && license === 'panoramax_in' ? 'Their public license is still Panoramax.' : ''}</p>
		{/if}
	{/if}
	{#if showLogin && $auth.checked && !$auth.is_authenticated}
		<p data-testid="contribution-login-notice"><a href="/login">Sign in or create an account</a> to upload. Signing in does not select a license or enable automatic uploads.</p>
	{/if}
</div>

<style>
	.summary { background: #f1f5f9; border-radius: .5rem; padding: .75rem 1rem; color: #1f2937; font-size: 1rem; line-height: 1.5; margin: .75rem 0; }
	p { margin: .35rem 0; }
	a { color: #1d4ed8; text-decoration: underline; }
</style>
