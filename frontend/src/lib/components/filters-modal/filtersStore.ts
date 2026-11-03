import { writable, derived, get } from 'svelte/store';
import { localStorageReadOnceSharedStore } from '$lib/svelte-shared-store';
import type { AnalysisFilters, PropertyFilters, QueryOptions } from '$lib/photoWorkerTypes';

const defaultAnalysis: AnalysisFilters = {
	time_of_day: null,
	location_type: null,
	min_farthest_distance: null,
	max_closest_distance: null,
	min_scenic_score: null,
	visibility_distance: null,
	tallest_building: null,
	features: [],
	show_unanalyzed: true
};

// Older installations stored analysis fields directly at the top level.
// The storage helper replaces defaults, so normalize before exposing the store.
// Saved values may also predate a field (the blur flags), hence partial properties.
type SavedFilters = { analysis?: Partial<AnalysisFilters>; properties?: Partial<PropertyFilters> };
export function normalizeFilters(value: SavedFilters | Partial<AnalysisFilters>): QueryOptions {
	const saved = value as SavedFilters & Partial<AnalysisFilters>;
	return {
		analysis: { ...defaultAnalysis, ...('analysis' in saved || 'properties' in saved ? saved.analysis : saved) },
		properties: { min_width: null, not_blurry: false, blurry: false, ...saved.properties }
	};
}

const defaultFilters = normalizeFilters({});
export const filters = localStorageReadOnceSharedStore<QueryOptions>('hillview_filters', defaultFilters);
filters.set(normalizeFilters(get(filters)));

// Override filters: temporarily shows filtered-out photos (toggled by long-pressing Filters button)
export const overrideFilters = writable<boolean>(false);

filters.subscribe(($filters) => {
	overrideFilters.set(false);
});


function countAnalysisFilters(analysis: AnalysisFilters): number {
	let count = 0;
	if (analysis.time_of_day) count++;
	if (analysis.location_type) count++;
	if (analysis.min_farthest_distance !== null) count++;
	if (analysis.max_closest_distance !== null) count++;
	if (analysis.min_scenic_score !== null) count++;
	if (analysis.visibility_distance) count++;
	if (analysis.tallest_building) count++;
	if (analysis.features.length > 0) count++;
	return count;
}

function countPropertyFilters(properties: QueryOptions['properties']): number {
	return (properties.min_width !== null ? 1 : 0) + (properties.not_blurry ? 1 : 0) + (properties.blurry ? 1 : 0);
}

function countFilters({ analysis, properties }: QueryOptions): number {
	return countAnalysisFilters(analysis) + countPropertyFilters(properties);
}

export const activeAnalysisFilterCount = derived(filters, ({ analysis }) => countAnalysisFilters(analysis));
export const hasActiveAnalysisFilters = derived(activeAnalysisFilterCount, count => count > 0);
export const activeFilterCount = derived(filters, countFilters);
export const hasActiveFilters = derived(activeFilterCount, ($count) => $count > 0);

export function clearFilters(): void {
	// Skip the no-op set: filters.set notifies subscribers even when the value is
	// unchanged, and an active timeline walk reloads its window on any filters
	// notification — whose completion re-asserts the cursor photo and can clobber
	// a ?photo= URL navigation (clearFilters is called on every such navigation).
	if (JSON.stringify(get(filters)) === JSON.stringify(defaultFilters)) return;
	filters.set(normalizeFilters({}));
}

export function buildFiltersQueryParam(): string | null {
	// Workers call this inside filters.subscribe, before derived stores may have
	// received the notification. Read and count the current value directly.
	const current = get(filters);
	return countFilters(current) > 0 ? JSON.stringify(current) : null;
}

// Modal state
export type FiltersModalState = {
	visible: boolean;
};

export const filtersModalState = writable<FiltersModalState>({ visible: false });

export function openFiltersModal(): void {
	filtersModalState.set({ visible: true });
}

export function closeFiltersModal(): void {
	filtersModalState.set({ visible: false });
}
