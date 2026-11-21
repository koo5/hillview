import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import type { PhotoData } from '$lib/types/photoTypes';
import { fetchPublicInfo, getCachedPublicInfo } from '$lib/photoExif';
import PhotoInfoWindow from './PhotoInfoWindow.svelte';

vi.mock('$lib/http', () => ({ http: { get: vi.fn() } }));
vi.mock('$lib/data.svelte', async () => {
	const { writable } = await import('svelte/store');
	return { showPhotoInfoWindow: writable(true), sources: writable([]) };
});
vi.mock('$lib/photoExif', async importOriginal => ({
	...await importOriginal<typeof import('$lib/photoExif')>(),
	fetchPublicInfo: vi.fn(),
	getCachedPublicInfo: vi.fn(),
}));

const photo = {
	id: 'a', uid: 'hillview-a', source: 'hillview', source_type: 'stream',
	filename: 'a.jpg', url: '/a.jpg', coord: { lat: 50, lng: 14 }, bearing: 90, altitude: 0,
} as PhotoData;

beforeEach(() => {
	vi.clearAllMocks();
	vi.mocked(getCachedPublicInfo).mockReturnValue(undefined);
	vi.mocked(fetchPublicInfo).mockResolvedValue(null);
});
afterEach(cleanup);

it.each(['map', 'zoom'] as const)('shows the fetched pitch and roll in the %s overlay', async variant => {
	vi.mocked(fetchPublicInfo).mockResolvedValue({ exif: null, pitch: 6.5, roll: -4.2 });
	render(PhotoInfoWindow, { photo, variant });
	await waitFor(() => expect(screen.getByTestId('photo-info-pitch')).toHaveTextContent('+6.5°'));
	expect(screen.getByTestId('photo-info-roll')).toHaveTextContent('-4.2°');
});

it('shows recorded zeroes and says when pose was not recorded', async () => {
	vi.mocked(fetchPublicInfo).mockResolvedValue({ exif: null, pitch: 0, roll: 0 });
	const component = render(PhotoInfoWindow, { photo });
	await waitFor(() => expect(screen.getByTestId('photo-info-pitch')).toHaveTextContent('0.0°'));
	expect(screen.getByTestId('photo-info-roll')).toHaveTextContent('0.0°');
	vi.mocked(fetchPublicInfo).mockResolvedValue(null);
	await component.rerender({ photo: { ...photo, id: 'b', uid: 'hillview-b' } });
	await waitFor(() => expect(screen.getByTestId('photo-info-pitch')).toHaveTextContent('Not recorded'));
	expect(screen.getByTestId('photo-info-roll')).toHaveTextContent('Not recorded');
});

it('also uses pose already carried by a non-Hillview photo', () => {
	render(PhotoInfoWindow, { photo: { ...photo, uid: 'panoramax-a', source: 'panoramax', pitch: -3, roll: 0 } });
	expect(screen.getByTestId('photo-info-pitch')).toHaveTextContent('-3.0°');
	expect(screen.getByTestId('photo-info-roll')).toHaveTextContent('0.0°');
	expect(fetchPublicInfo).not.toHaveBeenCalled();
});
