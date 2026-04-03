import { readable } from 'svelte/store';
import { browser } from '$app/environment';

/** True when the primary pointer is coarse (touch screen). Reactive to changes (e.g. device mode toggle in devtools). */
export const isTouchDevice = readable(false, (set) => {
	if (!browser) return;

	const mql = window.matchMedia('(pointer: coarse)');
	set(mql.matches);

	function onChange(e: MediaQueryListEvent) {
		set(e.matches);
	}
	mql.addEventListener('change', onChange);
	return () => mql.removeEventListener('change', onChange);
});
