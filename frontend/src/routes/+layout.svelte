<script lang="ts">
	import {onMount} from 'svelte';
	import {setupDeepLinkListener} from '$lib/authCallback';
	import {TAURI} from '$lib/tauri';
	import AuthStatusWatcher from '../components/AuthStatusWatcher.svelte';
	import {beforeNavigate, afterNavigate} from '$app/navigation';
	import {page} from '$app/stores';
	import {get} from 'svelte/store';
	import {clearAlerts} from "$lib/alertSystem.svelte";

	// Log navigation events
	beforeNavigate((navigation) => {
		clearAlerts();
		const currentPath = get(page).url.pathname;
		const newPath = navigation.to?.url.pathname;
		console.log(`🧭 [NAV] beforeNavigate: Navigating from "${currentPath}" to "${newPath}" (type: ${navigation.type})`);
	});

	afterNavigate((navigation) => {
		const currentPath = get(page).url.pathname;
		console.log(`🧭 [NAV] Navigation complete: now at "${currentPath}" (type: ${navigation.type})`);

		// Log additional page info
		const pageData = get(page);
		if (pageData.params && Object.keys(pageData.params).length > 0) {
			console.log(`🧭 [NAV] Page params:`, pageData.params);
		}
		if (pageData.url.search) {
			console.log(`🧭 [NAV] Query params:`, pageData.url.search);
		}
	});

	onMount(async () => {
		// Log initial page load
		const initialPath = get(page).url.pathname;
		console.log(`🧭 [NAV] Initial page load: "${initialPath}"`);

		if (TAURI) {
			await setupDeepLinkListener();
		}
	});
</script>

<slot/>
<AuthStatusWatcher/>
