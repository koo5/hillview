<script lang="ts">
	import '../app.css';
	import {browser} from '$app/environment';
	import {page} from '$app/stores';
	import {get} from 'svelte/store';
	import {onMount} from 'svelte';
	import {beforeNavigate, afterNavigate} from '$app/navigation';
	import {invoke} from '@tauri-apps/api/core';

	import {TAURI_MOBILE, TAURI} from '$lib/tauri';
	import {track} from '$lib/analytics';
	import {backendUrl} from '$lib/config';
	import {setupDeepLinkListener} from '$lib/authCallback';
	import AuthStatusWatcher from '$lib/components/AuthStatusWatcher.svelte';
	import ZoomView from '$lib/components/ZoomView.svelte';
	import DropdownMenu from '$lib/components/dropdown-menu/DropdownMenu.svelte';
	import {clearAlerts} from "$lib/alertSystem.svelte";
	import {checkAuth} from '$lib/auth.svelte';
	import {zoomViewData, pendingZoomView} from '$lib/zoomView.svelte';
	import {getCurrent} from "@tauri-apps/plugin-deep-link";
	import {navigateWithHistory} from "$lib/navigation.svelte";
	import {kotlinMessageQueue} from '$lib/KotlinMessageQueue';
	import {app, onAppActivityChange} from "$lib/data.svelte";
	import { ACTIVITY_NOTIFICATION_REFRESH_EVENT, shouldRefreshActivityFromNotification } from '$lib/notificationRouteUtils';
	import InsetGradients from "$lib/components/InsetGradients.svelte";
	import SignInModal from "$lib/components/SignInModal.svelte";
	import NavigationMenu from '$lib/components/NavigationMenu.svelte';
	import { navigationMenuOpen, closeNavigationMenu } from '$lib/navigationMenuStore';

	interface SafeAreaInsets {
		top: number;
		bottom: number;
		left: number;
		right: number;
		keyboardHeight?: number;
		keyboardVisible?: boolean;
	}


	// Log navigation events
	beforeNavigate((navigation) => {
		clearAlerts();
		const currentPath = get(page).url.pathname;
		const newPath = navigation.to?.url.pathname;
		// The zoom view is a global fullscreen photo overlay (rendered in this
		// layout, opened from the map or a photo page). It must not survive a route
		// change — otherwise e.g. opening a zoomview share link and hitting Back
		// leaves it stuck open over the new page. Close it whenever the pathname
		// changes; the destination re-opens it from x1..y2 URL params if warranted
		// (see Map.svelte). A same-route query change (map pan) is left alone.
		if (newPath && newPath !== currentPath) {
			zoomViewData.set(null);
			pendingZoomView.set(null);
		}
		console.log(`🢄🧭 [NAV] beforeNavigate: Navigating from "${currentPath}" to "${newPath}" (type: ${navigation.type})`);
	});

	afterNavigate((navigation) => {
		const currentPath = get(page).url.pathname;
		track('pageview:' + currentPath);
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

	onMount(async () => {

		/*try{
			await invoke('plugin:edge-to-edge|disable');
			console.log('Safe area Edge-to-edge mode disabled.');
		} catch(e) {
			console.error('Error disabling Safe area edge-to-edge mode:', e);
		}*/

		/*window.document.documentElement.style.setProperty("--safe-area-inset-top", "0px");
		window.document.documentElement.style.setProperty("--safe-area-inset-bottom", "0px");
		window.document.documentElement.style.setProperty("--safe-area-inset-left", "0px");
		window.document.documentElement.style.setProperty("--safe-area-inset-right", "0px");
		*/
		window.document.documentElement.style.setProperty("--keyboard-height", "0px");
		window.document.documentElement.style.setProperty("--keyboard-visible", "0");


		window?.addEventListener('safeAreaChanged', (event) => {
		  const detail = (event as CustomEvent<SafeAreaInsets>).detail;
		  console.log('Safe area changed:', JSON.stringify(detail));
		  window.document.documentElement.style.setProperty("--safe-area-inset-top", detail.top + "px");
		  window.document.documentElement.style.setProperty("--safe-area-inset-bottom", detail.bottom + "px");
		  window.document.documentElement.style.setProperty("--safe-area-inset-left", detail.left + "px");
		  window.document.documentElement.style.setProperty("--safe-area-inset-right", detail.right + "px");
		  window.document.documentElement.style.setProperty("--keyboard-height", (detail.keyboardHeight ?? 0) + "px");
		  window.document.documentElement.style.setProperty("--keyboard-visible", detail.keyboardVisible ? "1" : "0");
		});

		if (TAURI)
		{
			try {
				const safeArea = await invoke<SafeAreaInsets>('plugin:edge-to-edge|get_safe_area_insets');
				console.log('Initial safe area insets:', JSON.stringify(safeArea));
				window.document.documentElement.style.setProperty("--safe-area-inset-top", safeArea.top + "px");
				window.document.documentElement.style.setProperty("--safe-area-inset-bottom", safeArea.bottom + "px");
				window.document.documentElement.style.setProperty("--safe-area-inset-left", safeArea.left + "px");
				window.document.documentElement.style.setProperty("--safe-area-inset-right", safeArea.right + "px");
			} catch(e) {
				console.error('Error invoking Safe area get_safe_area_insets:', e);
			}
		}

		//await handleDeepLinkIntent();
		await handleIntentData();

		const initialPath = get(page).url.pathname;
		console.log(`🢄🧭 [NAV] Initial page load: "${initialPath}"`);

		// Initialize auth state for all pages
		checkAuth();

		if (TAURI) {
			await setupDeepLinkListener();
		}

		if (TAURI_MOBILE) {
			// Start message queue polling and handle notification clicks
			kotlinMessageQueue.startPolling();
			kotlinMessageQueue.on('notification-click', handleNotificationClick);
		}

		onAppActivityChange($app.activity);

		// Load Umami analytics (web only, not in Tauri/Android)
		if (!TAURI && import.meta.env.VITE_UMAMI_WEBSITE_ID) {
			const script = document.createElement('script');
			script.defer = true;
			script.src = import.meta.env.VITE_UMAMI_URL + '/script.js';
			script.dataset.websiteId = import.meta.env.VITE_UMAMI_WEBSITE_ID;
			script.dataset.autoTrack = 'false';
			document.head.appendChild(script);
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
    			await handleNotificationClickRoute(route);
			}

		} catch (error) {
			console.error('🢄📱 Error retrieving intent data:', error);
		}
	}

	async function handleNotificationClick(message: any)
	{
		const route = message.payload?.route;
		if (route) {
			console.log('🔔 Notification click received, navigating to:', route);
			await handleNotificationClickRoute(route);
		}
	}

	async function handleNotificationClickRoute(route: string)
	{
		app.update(a => ({...a, activity: 'view'}));
		const currentPath = get(page).url.pathname;
		const shouldRefreshActivity = shouldRefreshActivityFromNotification(currentPath, route);
		try {
			await navigateWithHistory(route);
			if (shouldRefreshActivity) {
				window.dispatchEvent(new CustomEvent(ACTIVITY_NOTIFICATION_REFRESH_EVENT));
			}
		} catch (error) {
			console.error('Error navigating to route from notification click:', error);
		}
	}


</script>


<svelte:head>
	{#if backendUrl !== 'https://api.hillview.cz/api'}
		<link rel="icon" href="/favicon-dev.png" type="image/png" />
	{/if}
</svelte:head>

<slot/>
<NavigationMenu isOpen={$navigationMenuOpen} onClose={closeNavigationMenu} />
<AuthStatusWatcher/>
<DropdownMenu/>
<ZoomView/>
<InsetGradients />
<SignInModal/>
