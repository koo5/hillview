import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import FiltersModal from './FiltersModal.svelte';
import { filters, filtersModalState, normalizeFilters } from './filtersStore';

vi.mock('$app/environment', () => ({ browser: true }));
vi.mock('$lib/analytics', () => ({ track: vi.fn() }));
vi.mock('$lib/data.svelte', async () => {
	const { writable } = await import('svelte/store');
	return { maxPhotosInArea: writable(100) };
});

beforeEach(() => {
	filters.set(normalizeFilters({}));
	filtersModalState.set({ visible: true });
});
afterEach(cleanup);

it('previews width during dragging, commits on change, and clears to any width', async () => {
	render(FiltersModal);
	const slider = screen.getByRole('slider', { name: 'Minimum Width' });
	const unanalyzed = screen.getByRole('checkbox', { name: 'Show unanalyzed photos' });
	expect(slider).toHaveValue('0');
	expect(unanalyzed).toBeDisabled();
	await fireEvent.input(slider, { target: { value: '3000' } });
	expect(screen.getByTestId('min-width-value')).toHaveTextContent('3,000 px');
	expect(get(filters).properties.min_width).toBeNull();
	await fireEvent.change(slider);
	expect(get(filters).properties.min_width).toBe(3000);
	expect(unanalyzed).toBeDisabled();
	await fireEvent.click(screen.getByRole('button', { name: 'Clear all filters' }));
	expect(slider).toHaveValue('0');
	expect(screen.getByTestId('min-width-value')).toHaveTextContent('Any width');
	expect(get(filters).properties.min_width).toBeNull();
});

it('keeps width when toggling analysis filters and enables the analysis option', async () => {
	filters.set(normalizeFilters({ properties: { min_width: 4000 } }));
	render(FiltersModal);
	expect(screen.getByRole('slider')).toHaveValue('4000');
	await fireEvent.click(screen.getByRole('button', { name: /^Day$/ }));
	expect(get(filters).analysis.time_of_day).toBe('day');
	expect(get(filters).properties.min_width).toBe(4000);
	const unanalyzed = screen.getByRole('checkbox', { name: 'Show unanalyzed photos' });
	expect(unanalyzed).toBeEnabled();
	await fireEvent.click(unanalyzed);
	expect(get(filters).analysis.show_unanalyzed).toBe(false);
});

it('toggles "Not blurry" as a property filter, independent of analysis', async () => {
	render(FiltersModal);
	const notBlurry = screen.getByRole('button', { name: 'Not blurry' });
	await fireEvent.click(notBlurry);
	expect(get(filters).properties.not_blurry).toBe(true);
	expect(get(filters).properties.blurry).toBe(false);
	// a property filter: does not enable the analysis-only "show unanalyzed" option
	expect(screen.getByRole('checkbox', { name: 'Show unanalyzed photos' })).toBeDisabled();
	expect(screen.getByRole('button', { name: 'Clear all filters' })).toBeEnabled();
	await fireEvent.click(notBlurry);
	expect(get(filters).properties.not_blurry).toBe(false);
});

it('hides the "Blurry" view outside DEV_MODE', () => {
	vi.stubEnv('VITE_DEV_MODE', 'false');
	render(FiltersModal);
	expect(screen.queryByRole('button', { name: 'Blurry (dev)' })).toBeNull();
	vi.unstubAllEnvs();
});

it('makes "Not blurry" and the DEV "Blurry" view exclusive', async () => {
	vi.stubEnv('VITE_DEV_MODE', 'true');
	render(FiltersModal);
	await fireEvent.click(screen.getByRole('button', { name: 'Not blurry' }));
	await fireEvent.click(screen.getByRole('button', { name: 'Blurry (dev)' }));
	expect(get(filters).properties).toMatchObject({ not_blurry: false, blurry: true });
	await fireEvent.click(screen.getByRole('button', { name: 'Clear all filters' }));
	expect(get(filters).properties).toMatchObject({ not_blurry: false, blurry: false });
	vi.unstubAllEnvs();
});
