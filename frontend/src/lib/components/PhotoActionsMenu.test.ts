import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { auth } from '../authStore';
import { deletePhotoRequest } from '../photoActions';
import { zoomViewData } from '../zoomView.svelte';
import type { PhotoData } from '../sources';
import PhotoActionsMenu from './PhotoActionsMenu.svelte';

vi.mock('$lib/auth.svelte.js', async () => import('../authStore'));
vi.mock('$lib/navigation.svelte', () => ({ navigateWithHistory: vi.fn() }));
vi.mock('$lib/shareUtils', () => ({ sharePhoto: vi.fn() }));
vi.mock('$lib/urlUtils', () => ({ openExternalUrl: vi.fn(), HILLVIEW_BASE_URL: '' }));
vi.mock('./signInModal.svelte', () => ({ requireAuth: vi.fn(() => true) }));
vi.mock('$lib/photoUtils', () => ({
	getPhotoSource: (photo: PhotoData) => photo.source,
	getUserName: () => 'owner',
	getUserId: () => 'owner-id',
	formatCapturedAt: () => '',
	getCanonicalPhotoUrl: () => null,
	getLicenseLabel: () => null,
	getLicenseId: () => null,
	getLicenseUrl: () => null,
	licenseUrlFor: () => '',
	getUserProfileUrl: () => ''
}));
vi.mock('$lib/photoActions', () => ({
	deletePhotoRequest: vi.fn(async () => ({ success: true, message: 'Photo deleted', error: false })),
	fetchPhotoRating: vi.fn(async () => ({ userRating: null, ratingCounts: { thumbs_up: 0, thumbs_down: 0 } })),
	fetchIsFlagged: vi.fn(async () => false),
	ratingShortcutFor: vi.fn(() => null),
	hidePhotoRequest: vi.fn(),
	togglePhotoRating: vi.fn(),
	unflagPhotoRequest: vi.fn(),
	flagPhotoRequest: vi.fn(),
	viewPhotoUserProfile: vi.fn(),
	openPhotoDetailPage: vi.fn()
}));

const photo = {
	id: 'photo-id', uid: 'hillview-photo-id', source: 'hillview', coord: { lat: 50, lng: 14 }
} as PhotoData;

function pressDelete(target: HTMLElement | Window = window, options: KeyboardEventInit = {}) {
	return fireEvent.keyDown(target, { key: 'Delete', ...options });
}

beforeEach(() => {
	vi.clearAllMocks();
	auth.set({
		is_authenticated: true, checked: true, userStatus: 'loaded', refresh_status: 'idle',
		user: { id: 'admin-id', username: 'admin', email: '', role: 'admin' }
	});
	zoomViewData.set(null);
});

afterEach(() => {
	cleanup();
	document.body.replaceChildren();
});

it('opens the current photo confirmation from the map or gallery and focuses Delete', async () => {
	render(PhotoActionsMenu, { photo });
	const map = document.createElement('div');
	map.tabIndex = 0;
	document.body.append(map);
	map.focus();
	await pressDelete(map);
	expect(screen.getByTestId('delete-photo-dialog')).toBeVisible();
	await waitFor(() => expect(screen.getByTestId('delete-photo-confirm')).toHaveFocus());
	expect(deletePhotoRequest).not.toHaveBeenCalled();
	await pressDelete(screen.getByTestId('delete-photo-confirm'));
	expect(deletePhotoRequest).not.toHaveBeenCalled();
	await fireEvent.click(screen.getByTestId('delete-photo-cancel'));

	const galleryButton = screen.getByTestId('thumbs-up-button');
	galleryButton.focus();
	await pressDelete(galleryButton);
	await waitFor(() => expect(screen.getByTestId('delete-photo-confirm')).toHaveFocus());
	await fireEvent.click(screen.getByTestId('delete-photo-confirm'));
	expect(deletePhotoRequest).toHaveBeenCalledWith(photo, undefined);
});

it.each(['user', 'moderator', 'admin'])('respects the %s role', async (role) => {
	auth.update(state => ({ ...state, user: { ...state.user!, role } }));
	render(PhotoActionsMenu, { photo });
	await pressDelete();
	expect(!!screen.queryByTestId('delete-photo-dialog')).toBe(role !== 'user');
});

it.each([null, { ...photo, source: 'panoramax' }])('ignores unavailable or external photos', async (targetPhoto) => {
	render(PhotoActionsMenu, { photo: targetPhoto });
	await pressDelete();
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});

it.each(['input', 'textarea', 'select', 'contenteditable'])('leaves Delete alone in %s', async (field) => {
	render(PhotoActionsMenu, { photo });
	const editor = document.createElement(field === 'contenteditable' ? 'div' : field);
	if (field === 'contenteditable') editor.contentEditable = 'true';
	document.body.append(editor);
	editor.focus();
	await pressDelete(editor);
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});

it.each<KeyboardEventInit>([
	{ ctrlKey: true }, { altKey: true }, { metaKey: true }, { shiftKey: true },
	{ repeat: true }, { isComposing: true }
])('ignores modified, repeated, or composing Delete: %j', async (options) => {
	render(PhotoActionsMenu, { photo });
	await pressDelete(window, options);
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});

it('respects events already handled by the focused view', async () => {
	render(PhotoActionsMenu, { photo });
	const event = new KeyboardEvent('keydown', { key: 'Delete', cancelable: true });
	event.preventDefault();
	await fireEvent(window, event);
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});

it('leaves another dialog in control of the keyboard', async () => {
	render(PhotoActionsMenu, { photo });
	const dialog = document.createElement('div');
	dialog.setAttribute('role', 'dialog');
	const button = document.createElement('button');
	dialog.append(button);
	document.body.append(dialog);
	button.focus();
	await pressDelete(button);
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});

it('does not target the gallery photo behind the zoom viewer', async () => {
	zoomViewData.set({ url: 'photo.jpg', fallback_url: 'photo.jpg', filename: 'photo.jpg' });
	render(PhotoActionsMenu, { photo });
	await pressDelete();
	expect(screen.queryByTestId('delete-photo-dialog')).toBeNull();
});
