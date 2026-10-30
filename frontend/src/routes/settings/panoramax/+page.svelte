<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
</script>

<svelte:head><title>Contributing to Panoramax - Hillview</title></svelte:head>
<StandardHeaderWithAlert title="Contributing to Panoramax" showMenuButton={true} fallbackHref="/settings/upload" />
<StandardBody>
	<article data-testid="panoramax-info">
		<h1>Contributing to Panoramax</h1>
		<h2>Your grant and the published license</h2>
		<p>The upload license is the grant you give Hillview. The public license governs reuse of the published photo. <a href="/licensing">Read about each license</a>.</p>
		<p>Full rights to Hillview and the Panoramax contribution grant allow sharing. CC BY-SA 4.0 + OSM alone does not cover the federation’s derived-data uses.</p>
		<p>Full rights photos are published as Panoramax when sharing is on, otherwise as all rights reserved with the OSM mapping grant. The Panoramax contribution grant always publishes as Panoramax, with sharing on or off. The final Panoramax license wording is pending.</p>
		<h2>Choose which photos to offer</h2>
		<p>The P button above camera settings changes the default for future browser captures. Settings uses the same default. File uploads have a separate sharing choice for the next batch. Neither control changes an existing photo, chooses a license, signs you in or enables uploads.</p>
		<p>Every capture keeps its sharing choice and its selected upload grant. A photo captured before you choose a license adopts your upload license when it uploads. You can change an existing photo’s sharing choice on its photo page.</p>
		<h2>Sign-in and uploads</h2>
		<p>You can capture and choose preferences before signing in. Uploading requires an account, an upload license and an explicit upload action or automatic-upload opt-in. Queued photos can upload after sign-in when automatic uploads are already enabled.</p>
		<h2>Anonymization and moderation</h2>
		<p>Only photos checked by the detector with no blurred boxes qualify. Photos with anonymization doodles, manual rectangles or skipped blurring are excluded. Moderators can withhold approval for a photo or disable an account’s contributions. Other visibility, processing and quality checks still apply.</p>
		<h2>Representative views</h2>
		<p>Sharing offers a photo for consideration. Hillview selects one view per 5 m grid cell and bearing sector, preferring daytime and then newer captures. Not every eligible photo appears in the catalog.</p>
		<h2>Copies may remain</h2>
		<p>Turning sharing off stops future federation from Hillview. Copies already collected or reused elsewhere may remain available.</p>
		<p><a href="/settings/upload">Choose capture and upload preferences</a></p>
	</article>
</StandardBody>

<style>
	article { max-width: 48rem; margin: 0 auto; font-size: 1rem; line-height: 1.65; }
	h1 { font-size: 1.75rem; }
	h2 { margin-top: 1.5rem; font-size: 1.25rem; }
	a { color: #1d4ed8; text-decoration: underline; }
</style>
