import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import SearchPane from './SearchPane.svelte';
import { searchPlaces, type PlaceResult } from '$lib/placesApi';

vi.mock('$lib/placesApi', () => ({ searchPlaces: vi.fn() }));
const place: PlaceResult = {
	id: '42', name: 'Praha', display_name: 'Praha, Česko', lat: 50.0875, lon: 14.4213,
	bounds: [49.94, 50.18, 14.22, 14.71]
};
const searchMock = vi.mocked(searchPlaces);

afterEach(() => { cleanup(); vi.resetAllMocks(); });

async function submit(query: string) {
	await fireEvent.input(screen.getByTestId('place-search-input'), { target: { value: query } });
	await fireEvent.submit(screen.getByRole('search'));
}

describe('place search panel', () => {
	it('offers pasted coordinates without a geocoder request', async () => {
		const onSelect = vi.fn();
		render(SearchPane, { onSelect });
		await submit('50°10\'29.869"N, 14°38\'52.907"E');
		const result = await screen.findByTestId('place-search-result');
		expect(result).toHaveTextContent('50.1749636, 14.6480297');
		expect(searchMock).not.toHaveBeenCalled();
		await fireEvent.click(result);
		expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ lat: 50.1749636, lon: 14.6480297 }));
		expect(screen.queryByTestId('place-attribution')).toBeNull();
	});

	it('searches on submit and moves only when a result is selected', async () => {
		searchMock.mockResolvedValue([place]);
		const onSelect = vi.fn();
		render(SearchPane, { onSelect });
		await fireEvent.input(screen.getByTestId('place-search-input'), { target: { value: 'Praha' } });
		expect(searchMock).not.toHaveBeenCalled();
		await fireEvent.submit(screen.getByRole('search'));
		const result = await screen.findByTestId('place-search-result');
		expect(result).toHaveTextContent('Praha, Česko');
		expect(onSelect).not.toHaveBeenCalled();
		await fireEvent.click(result);
		expect(onSelect).toHaveBeenCalledWith(place);
		expect(result).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByTestId('place-attribution')).toBeVisible();
	});

	it('shows empty results and allows retrying after an error', async () => {
		searchMock.mockRejectedValueOnce(new Error('Try again')).mockResolvedValueOnce([]);
		render(SearchPane, { onSelect: vi.fn() });
		await submit('nowhere');
		expect(await screen.findByTestId('place-search-error')).toHaveTextContent('Try again');
		await fireEvent.submit(screen.getByRole('search'));
		expect(await screen.findByTestId('place-search-empty')).toBeVisible();
		expect(screen.queryByTestId('place-search-error')).toBeNull();
	});

	it('cancels an old query and ignores its late response', async () => {
		let resolveOld!: (value: PlaceResult[]) => void;
		searchMock.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
		searchMock.mockResolvedValueOnce([]);
		render(SearchPane, { onSelect: vi.fn() });
		await submit('Praha');
		expect(screen.getByTestId('place-search-loading')).toBeVisible();
		const oldSignal = searchMock.mock.calls[0][1];
		await submit('Brno');
		expect(oldSignal.aborted).toBe(true);
		await screen.findByTestId('place-search-empty');
		resolveOld([place]);
		await waitFor(() => expect(screen.queryByTestId('place-search-result')).toBeNull());
	});

	it('cancels an in-flight request when leaving the activity', async () => {
		searchMock.mockImplementation(() => new Promise(() => {}));
		const { unmount } = render(SearchPane, { onSelect: vi.fn() });
		await submit('Praha');
		const signal = searchMock.mock.calls[0][1];
		unmount();
		expect(signal.aborted).toBe(true);
	});

	it('waits for the map before allowing result selection', async () => {
		const onSelect = vi.fn();
		const { rerender } = render(SearchPane, { onSelect, canSelect: false });
		await submit('50.1, 14.5');
		expect(screen.getByTestId('place-search-result')).toBeDisabled();
		expect(onSelect).not.toHaveBeenCalled();
		await rerender({ canSelect: true });
		expect(screen.getByTestId('place-search-result')).toBeEnabled();
	});
});
