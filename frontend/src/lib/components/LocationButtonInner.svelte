<script lang="ts">
	import {LocateFixed} from 'lucide-svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import {locationTrackingLoading} from '$lib/locationManager';

	export let showSpinner = true;
</script>

<LocateFixed />
{#if showSpinner && $locationTrackingLoading}
	<Spinner show={true} color="#4285F4"></Spinner>
{/if}
