import { writable, derived, get } from 'svelte/store';
import { localStorageReadOnceSharedStore } from '$lib/svelte-shared-store';
import type { QueryOptions } from '$lib/photoWorkerTypes';

export type { QueryOptions };

const defaultFilters: QueryOptions = {
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

export const filters = localStorageReadOnceSharedStore<QueryOptions>('hillview_filters', defaultFilters);

// Override filters: temporarily shows filtered-out photos (toggled by long-pressing Filters button)
export const overrideFilters = writable<boolean>(false);

filters.subscribe(($filters) => {
	overrideFilters.set(false);
});


export const activeFilterCount = derived(filters, ($filters) => {
	let count = 0;
	if ($filters.time_of_day) count++;
	if ($filters.location_type) count++;
	if ($filters.min_farthest_distance !== null) count++;
	if ($filters.max_closest_distance !== null) count++;
	if ($filters.min_scenic_score !== null) count++;
	if ($filters.visibility_distance) count++;
	if ($filters.tallest_building) count++;
	if ($filters.features.length > 0) count++;
	return count;
});

export const hasActiveFilters = derived(activeFilterCount, ($count) => $count > 0);

export function clearFilters(): void {
	// Skip the no-op set: filters.set notifies subscribers even when the value is
	// unchanged, and an active timeline walk reloads its window on any filters
	// notification — whose completion re-asserts the cursor photo and can clobber
	// a ?photo= URL navigation (clearFilters is called on every such navigation).
	if (JSON.stringify(get(filters)) === JSON.stringify(defaultFilters)) return;
	filters.set(defaultFilters);
}

export function buildFiltersQueryParam(): string | null {
	const $filters = get(filters);
	const hasAnyFilter =
		$filters.time_of_day ||
		$filters.location_type ||
		$filters.min_farthest_distance !== null ||
		$filters.max_closest_distance !== null ||
		$filters.min_scenic_score !== null ||
		$filters.visibility_distance ||
		$filters.tallest_building ||
		$filters.features.length > 0;

	if (!hasAnyFilter) return null;

	return JSON.stringify($filters);
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
