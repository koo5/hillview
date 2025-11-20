<script lang="ts">
	import {browser} from '$app/environment';
	import {page} from '$app/stores';
	import {get} from 'svelte/store';
	import {onMount} from 'svelte';
	import {beforeNavigate, afterNavigate} from '$app/navigation';
	import {invoke} from '@tauri-apps/api/core';

	import {TAURI_MOBILE, TAURI} from '$lib/tauri';
	import {backendUrl} from '$lib/config';
	import {setupDeepLinkListener} from '$lib/authCallback';
	import AuthStatusWatcher from '$lib/components/AuthStatusWatcher.svelte';
	import ZoomView from '$lib/components/ZoomView.svelte';
	import {clearAlerts} from "$lib/alertSystem.svelte";
	import {checkAuth} from '$lib/auth.svelte';
	import {zoomViewData} from '$lib/zoomView.svelte';
	import {getCurrent} from "@tauri-apps/plugin-deep-link";
	import {navigateWithHistory} from "$lib/navigation.svelte";

	// Log navigation events
	beforeNavigate((navigation) => {
		clearAlerts();
		const currentPath = get(page).url.pathname;
		const newPath = navigation.to?.url.pathname;
		console.log(`🢄🧭 [NAV] beforeNavigate: Navigating from "${currentPath}" to "${newPath}" (type: ${navigation.type})`);
	});

	afterNavigate((navigation) => {
		const currentPath = get(page).url.pathname;
		console.log(`🢄🧭 [NAV] Navigation complete: now at "${currentPath}" (type: ${navigation.type})`);

		// Log additional page info
		const pageData = get(page);
		if (pageData.params && Object.keys(pageData.params).length > 0) {
			console.log(`🢄🧭 [NAV] Page params:`, pageData.params);
		}
		if (pageData.url.search) {
			console.log(`🢄🧭 [NAV] Query params:`, pageData.url.search);
		}
	});

	// Handle body scroll prevention for zoom view
	$: {
		if (browser && document?.body) {
			document.body.style.overflow = $zoomViewData ? 'hidden' : '';
		}
	}

	onMount(async () => {

		//await handleDeepLinkIntent();
		await handleIntentData();

		const initialPath = get(page).url.pathname;
		console.log(`🢄🧭 [NAV] Initial page load: "${initialPath}"`);

		// Initialize auth state for all pages
		checkAuth();

		if (TAURI) {
			await setupDeepLinkListener();
		}
	});


	async function handleDeepLinkIntent()
	{
		console.log('🢄🔗 ...');
		try {
			const current_activity = await getCurrent();
			console.log('🢄🔗 Current deep link activity:', current_activity);
			if (current_activity)
			{
				// navigate based on the deep link
				const route = '/' + current_activity[0].split('://')[1];
				console.log('🢄🔗 Navigating to route from deep link:', route);
				await navigateWithHistory(route);
			}
		}
		catch(e) {
			console.error('🢄🔗 getCurrent error:', e);
		}
	}

	async function handleIntentData()
	{
		if (!TAURI_MOBILE) return;

		console.log('🢄📱 Checking for intent data...');

		try {
			const intentData: any = await invoke('plugin:hillview|get_intent_data');
			console.log('🢄📱 Intent data received:', JSON.stringify(intentData));

			const route = intentData?.click_action;
			if (route) {
    			console.log('App launched from FCM notification intent!, navigating to:', route);
    			await navigateWithHistory(route);
			}

		} catch (error) {
			console.error('🢄📱 Error retrieving intent data:', error);
		}
	}

</script>

<slot/>
<AuthStatusWatcher/>
{#if $zoomViewData }
	<ZoomView/>
{/if}
