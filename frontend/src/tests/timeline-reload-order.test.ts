import { describe, it, expect, vi, beforeEach } from 'vitest';

// The walk reloads on every content-filter change. Two quick toggles mean two
// requests in flight; whichever response arrives last used to be installed, so a
// slower, older one could reinstate the unfiltered list (Playwright: timeline.spec
// "content filters narrow the walk", seen 2026-10-30 as "2 / 3" instead of
// "No photos").

vi.mock('$lib/http', () => ({ http: { get: vi.fn() } }));
vi.mock('$lib/alertSystem.svelte', () => ({ addAlert: vi.fn() }));
vi.mock('$lib/svelte-shared-store', async () => {
    const { writable } = await import('svelte/store');
    return { localStorageSharedStore: (_key: string, value: unknown) => writable(value) };
});
vi.mock('$lib/mapState', async () => {
    const { writable } = await import('svelte/store');
    return {
        photoInFront: writable(null),
        bearingState: writable({ photoUid: null, source: null }),
        timelinePinned: writable(new Set()),
        hunterMode: writable(true),
        setHunterMode: vi.fn(),
    };
});
vi.mock('$lib/components/filters-modal/filtersStore', async () => {
    const { writable, get } = await import('svelte/store');
    const filters = writable({ show_unanalyzed: true });
    return { filters, buildFiltersQueryParam: () => JSON.stringify(get(filters)) };
});

import { get } from 'svelte/store';
import { http } from '$lib/http';
import { filters } from '$lib/components/filters-modal/filtersStore';
import { startTimeline, stopTimeline, timelinePhotos, timelineLoading, timelineActive } from '$lib/timeline';

const httpGet = vi.mocked(http.get);

function photo(id: string) {
    return {
        id, lat: 50, lng: 14, bearing: 0, captured_at: '2026-01-01T00:00:00Z', uploaded_at: null,
        thumb_url: null, owner_id: 'u1', owner_username: 'bob',
    };
}

function response(ids: string[]) {
    return { ok: true, json: async () => ({ photos: ids.map(photo), anchor_index: 0 }) } as unknown as Response;
}

/** A pending http.get the test resolves when it chooses. */
function deferred() {
    let resolve!: (r: Response) => void;
    const promise = new Promise<Response>((r) => { resolve = r; });
    return { promise, resolve };
}

const ANCHOR = { id: 'a1', uid: 'hillview-a1', creator: { id: 'u1', username: 'bob' } } as any;

beforeEach(() => {
    stopTimeline();
    httpGet.mockReset();
});

describe('timeline reloads', () => {
    it('installs the newest reload even when an older one answers last', async () => {
        httpGet.mockResolvedValueOnce(response(['a1', 'a2', 'a3']));
        await startTimeline(ANCHOR);
        expect(get(timelinePhotos).map((p) => p.id)).toEqual(['a1', 'a2', 'a3']);

        const older = deferred();
        const newer = deferred();
        httpGet.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);

        filters.set({ show_unanalyzed: true, time_of_day: 'day' } as any);   // reload 1
        filters.set({ show_unanalyzed: false, time_of_day: 'day' } as any);  // reload 2
        expect(httpGet).toHaveBeenCalledTimes(3);

        newer.resolve(response([]));
        await vi.waitFor(() => expect(get(timelinePhotos)).toEqual([]));
        expect(get(timelineLoading)).toBe(false);

        older.resolve(response(['a1', 'a2', 'a3']));
        await new Promise((r) => setTimeout(r, 0));
        expect(get(timelinePhotos)).toEqual([]);   // the stale answer is dropped
        expect(get(timelineActive)).toBe(true);
    });

    it('keeps the loading flag up until the newest reload finishes', async () => {
        httpGet.mockResolvedValueOnce(response(['a1']));
        await startTimeline(ANCHOR);

        const older = deferred();
        const newer = deferred();
        httpGet.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
        filters.set({ show_unanalyzed: false } as any);
        filters.set({ show_unanalyzed: true } as any);

        older.resolve(response(['a1']));
        await new Promise((r) => setTimeout(r, 0));
        expect(get(timelineLoading)).toBe(true);

        newer.resolve(response(['a1', 'a2']));
        await vi.waitFor(() => expect(get(timelineLoading)).toBe(false));
        expect(get(timelinePhotos).map((p) => p.id)).toEqual(['a1', 'a2']);
    });
});
