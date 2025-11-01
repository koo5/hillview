<script lang="ts">
	import {onMount} from 'svelte';
	import {setupDeepLinkListener} from '$lib/authCallback';
	import {TAURI} from '$lib/tauri';
	import AuthStatusWatcher from '../components/AuthStatusWatcher.svelte';
	import {beforeNavigate, afterNavigate} from '$app/navigation';
	import {page} from '$app/stores';
	import {get} from 'svelte/store';
	import {clearAlerts} from "$lib/alertSystem.svelte";
	import {checkAuth} from '$lib/auth.svelte';
	import {backendUrl} from '$lib/config';
	import {TAURI_MOBILE} from '$lib/tauri';
	import {invoke} from '@tauri-apps/api/core';

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

	onMount(async () => {
		// Log initial page load
		const initialPath = get(page).url.pathname;
		console.log(`🢄🧭 [NAV] Initial page load: "${initialPath}"`);

		// Configure backend URL for Android features (push notifications, etc.)
		if (TAURI_MOBILE) {
			try {
				console.log('🢄🌐 [APP] Configuring backend URL on app load:', backendUrl);
				await invoke('plugin:hillview|set_backend_url', {
					backendUrl: backendUrl
				});
				console.log('🢄🌐 [APP] Backend URL configured successfully');
			} catch (error) {
				console.error('🢄🌐 [APP] Failed to configure backend URL:', error);
			}
		}

		// Initialize auth state for all pages
		checkAuth();

		if (TAURI) {
			await setupDeepLinkListener();
		}
	});
</script>

<slot/>
<AuthStatusWatcher/>
