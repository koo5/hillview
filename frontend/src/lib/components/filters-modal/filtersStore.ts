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

// All features organized by category (matching analyze_photo.py schema)
export const featureCategories = [
	{
		name: 'Nature',
		features: ['hill', 'mountain', 'river', 'stream', 'water_body', 'landscape', 'rock_outcrop', 'tree_lined_path', 'path', 'nature']
	},
	{
		name: 'Urban',
		features: ['street', 'building', 'cityscape', 'high_rise_building', 'church', 'playground', 'bench']
	},
	{
		name: 'Structures',
		features: ['bridge', 'tower', 'observation_tower', 'water_tower', 'cooling_tower', 'crane', 'curved_structure', 'mast']
	},
	{
		name: 'Infrastructure',
		features: ['lamp_post', 'powerline_pole', 'utility_pole', 'high_mast_lighting', 'row_of_streetlights', 'ev_charger']
	},
	{
		name: 'Activity',
		features: ['construction', 'roadworks', 'ski_slope', 'accident']
	},
	{
		name: 'Animals',
		features: ['cat', 'dog']
	},
	{
		name: 'Other',
		features: ['art', 'signage']
	}
];

// URL filters: links into the map can preset filters, e.g.
//   /?filters_cat=1&filters_show_unanalyzed=0&lat=50&lon=12&zoom=4
// Convention: every filter param is `filters_<name>`, so they are easy to tell apart
// from the position params (lat/lon/zoom/bearing/photo) and to strip as a group.
// A link's filters start from the defaults — the same ones the modal starts from —
// and set only what they name:
// - `filters_<feature>=1` — <feature> is a feature id from featureCategories, exactly
//   as stored (singular: filters_cat, not filters_cats). Several are OR-ed, as in the modal.
// - `filters_show_unanalyzed=0|1` — the AnalysisFilters field of that name. It defaults
//   to 1, so a link that promises cats must say 0, or every unanalyzed photo (all of
//   Panoramax, most of Hillview) shows up beside them.
// Unknown names and values are ignored with a warning, never guessed at.
export const FILTER_URL_PREFIX = 'filters_';

function parseUrlFlag(key: string, value: string): boolean | null {
	if (value === '1' || value === 'true') return true;
	if (value === '0' || value === 'false') return false;
	console.warn(`🢄URL filter ${key}=${value} ignored: expected 0 or 1`);
	return null;
}

export function filtersFromUrl(params: URLSearchParams): QueryOptions | null {
	const known = new Set(featureCategories.flatMap(c => c.features));
	const result = normalizeFilters({});
	let any = false;
	for (const [key, value] of params) {
		if (!key.startsWith(FILTER_URL_PREFIX)) continue;
		any = true;
		const name = key.slice(FILTER_URL_PREFIX.length);
		const flag = parseUrlFlag(key, value);
		if (flag === null) continue;
		if (name === 'show_unanalyzed') {
			result.analysis.show_unanalyzed = flag;
		} else if (known.has(name)) {
			if (flag && !result.analysis.features.includes(name)) result.analysis.features.push(name);
		} else {
			console.warn(`🢄Unknown URL filter ${key} ignored`);
		}
	}
	return any ? result : null;
}
