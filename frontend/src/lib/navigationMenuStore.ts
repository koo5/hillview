import { writable } from 'svelte/store';

/** Single source of truth for the NavigationMenu's open state.
 *  Consumed by the layout-level <NavigationMenu /> instance; mutated by any
 *  hamburger button (StandardHeader, Main, etc.). */
export const navigationMenuOpen = writable(false);

export function toggleNavigationMenu(): void {
	navigationMenuOpen.update((v) => !v);
}

export function closeNavigationMenu(): void {
	navigationMenuOpen.set(false);
}
