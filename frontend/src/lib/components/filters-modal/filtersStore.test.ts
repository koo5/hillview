import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: true }));

async function loadFilters(saved?: object) {
	vi.resetModules();
	localStorage.clear();
	if (saved) localStorage.setItem('hillview_filters', JSON.stringify(saved));
	return import('./filtersStore');
}

describe('Hillview filter state', () => {
	beforeEach(() => localStorage.clear());

	it('migrates saved flat analysis filters without losing preferences', async () => {
		const store = await loadFilters({ time_of_day: 'night', features: ['hill'], show_unanalyzed: false });
		const saved = get(store.filters);
		expect(saved.analysis.time_of_day).toBe('night');
		expect(saved.analysis.features).toEqual(['hill']);
		expect(saved.analysis.show_unanalyzed).toBe(false);
		expect(saved.analysis.min_scenic_score).toBeNull();
		expect(saved.properties.min_width).toBeNull();
		expect(get(store.activeFilterCount)).toBe(2);
		expect(JSON.parse(localStorage.getItem('hillview_filters')!)).toEqual(saved);
	});

	it('counts and serializes a property-only filter independently of analysis', async () => {
		const store = await loadFilters({ properties: { min_width: 4000 } });
		expect(get(store.activeFilterCount)).toBe(1);
		expect(get(store.hasActiveAnalysisFilters)).toBe(false);
		expect(JSON.parse(store.buildFiltersQueryParam()!)).toEqual({
			analysis: store.normalizeFilters({}).analysis,
			properties: { min_width: 4000, not_blurry: false, blurry: false }
		});
	});

	it('counts the blur flags as property filters and fills them in for older saved filters', async () => {
		const store = await loadFilters({ properties: { min_width: null, not_blurry: true, blurry: false } });
		expect(get(store.activeFilterCount)).toBe(1);
		expect(get(store.hasActiveAnalysisFilters)).toBe(false);
		expect(JSON.parse(store.buildFiltersQueryParam()!).properties.not_blurry).toBe(true);
		expect(store.normalizeFilters({ properties: { min_width: 3000 } }).properties)
			.toEqual({ min_width: 3000, not_blurry: false, blurry: false });
	});

	it('preserves nested analysis and property filters, then clears both', async () => {
		const store = await loadFilters({ analysis: { min_scenic_score: 4 }, properties: { min_width: 3000 } });
		expect(get(store.activeFilterCount)).toBe(2);
		expect(get(store.hasActiveAnalysisFilters)).toBe(true);
		store.overrideFilters.set(true);
		store.clearFilters();
		expect(get(store.activeFilterCount)).toBe(0);
		expect(get(store.overrideFilters)).toBe(false);
		expect(store.buildFiltersQueryParam()).toBeNull();
	});

	it('does not notify timeline listeners when clearing already-default filters', async () => {
		const store = await loadFilters();
		const listener = vi.fn();
		const unsubscribe = store.filters.subscribe(listener);
		listener.mockClear();
		store.clearFilters();
		expect(listener).not.toHaveBeenCalled();
		unsubscribe();
	});

	it('serializes current filters inside worker subscriptions regardless of derived subscription order', async () => {
		const store = await loadFilters();
		const listener = vi.fn();
		const stopWorker = store.filters.subscribe(() => listener(store.buildFiltersQueryParam()));
		const stopBadge = store.hasActiveFilters.subscribe(() => {});
		store.filters.update(f => ({ ...f, properties: { ...f.properties, min_width: 3000 } }));
		expect(JSON.parse(listener.mock.lastCall![0]).properties.min_width).toBe(3000);
		store.clearFilters();
		expect(listener.mock.lastCall![0]).toBeNull();
		stopWorker();
		stopBadge();
	});
});

describe('URL filters (filters_*)', () => {
	const parse = async (query: string) => (await loadFilters()).filtersFromUrl(new URLSearchParams(query));

	it('returns null when the URL names no filters, so saved filters are left alone', async () => {
		expect(await parse('lat=50&lon=12&zoom=4')).toBeNull();
	});

	it('builds the all-cats link filter from defaults plus only what it names', async () => {
		const store = await loadFilters({ time_of_day: 'night', features: ['hill'] });
		const f = store.filtersFromUrl(new URLSearchParams('filters_cat=1&filters_show_unanalyzed=0&lat=50&lon=12&zoom=4'))!;
		expect(f).toEqual(store.normalizeFilters({ analysis: { features: ['cat'], show_unanalyzed: false } }));
	});

	it('keeps show_unanalyzed at its default when the link does not set it', async () => {
		const f = (await parse('filters_dog=1'))!;
		expect(f.analysis.features).toEqual(['dog']);
		expect(f.analysis.show_unanalyzed).toBe(true);
	});

	it('ORs several features without duplicates, and 0 does not add one', async () => {
		const f = (await parse('filters_cat=1&filters_dog=true&filters_cat=1&filters_bench=0'))!;
		expect(f.analysis.features).toEqual(['cat', 'dog']);
	});

	it('ignores unknown names and bad values instead of guessing (no plural mapping)', async () => {
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const f = (await parse('filters_cats=1&filters_cat=yes&filters_show_unanalyzed=nope'))!;
		expect(f).toEqual((await loadFilters()).normalizeFilters({}));
		expect(warn).toHaveBeenCalledTimes(3);
		warn.mockRestore();
	});
});
