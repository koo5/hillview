import { writable, get } from 'svelte/store';
import { navigateWithHistory } from '$lib/navigation.svelte.js';
import { auth } from '$lib/auth.svelte.js';

export type SignInModalState = {
	visible: boolean;
	message: string;
};

const initialState: SignInModalState = {
	visible: false,
	message: 'Sign in to interact with photos.'
};

export const signInModalState = writable<SignInModalState>(initialState);

/**
 * Show the sign-in modal with an optional custom message.
 */
export function openSignInModal(message?: string): void {
	signInModalState.set({
		visible: true,
		message: message ?? initialState.message
	});
}

/**
 * Close the sign-in modal.
 */
export function closeSignInModal(): void {
	signInModalState.set(initialState);
}

/**
 * Close the modal and navigate to /login.
 */
export function signInAndNavigate(): void {
	closeSignInModal();
	navigateWithHistory('/login');
}

/**
 * Returns true if authenticated. Otherwise opens the sign-in modal and returns false.
 */
export function requireAuth(message?: string): boolean {
	if (get(auth).is_authenticated) return true;
	openSignInModal(message);
	return false;
}
