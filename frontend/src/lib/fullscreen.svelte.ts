import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export const isFullscreen = writable(false);

if (browser) {
	document.addEventListener('fullscreenchange', () => {
		isFullscreen.set(!!document.fullscreenElement);
	});
}

export function toggleFullscreen() {
	if (!document.fullscreenElement) {
		document.documentElement.requestFullscreen().then(() => {
			isFullscreen.set(true);
		}).catch(err => {
			console.warn('Fullscreen request failed:', err);
		});
	} else {
		document.exitFullscreen().then(() => {
			isFullscreen.set(false);
		});
	}
}
