/**
 * Marker set diffing — the pure half of OptimizedMarkerSystem.updateMarkers.
 *
 * The map's photo set is now republished several times per viewport (once per
 * source as it lands, then the settled set), so rebuilding every marker on
 * every publish would multiply the DOM churn by the number of sources. The
 * renderer instead keys markers by photo and only touches what changed; this
 * module decides what that is.
 */

export type MarkerKey = string;

export interface KeyedDiff<T> {
	/** In `next` but not in `previous` — needs a marker created. */
	added: T[];
	/** In both — the existing marker is refreshed in place. */
	kept: T[];
	/** In `previous` but not in `next` — the marker goes back to the pool. */
	removed: MarkerKey[];
	/** `next` with duplicate keys dropped (first wins), in `next` order. */
	ordered: T[];
}

/** A photo's identity across publishes: the source-qualified uid, else the id. */
export function markerKey(photo: { uid?: string; id: string }): MarkerKey {
	return photo.uid ?? photo.id;
}

export function diffByKey<T>(
	previous: Iterable<MarkerKey>,
	next: T[],
	keyOf: (item: T) => MarkerKey
): KeyedDiff<T> {
	const prev = new Set(previous);
	const seen = new Set<MarkerKey>();
	const added: T[] = [];
	const kept: T[] = [];
	const ordered: T[] = [];

	for (const item of next) {
		const key = keyOf(item);
		if (seen.has(key)) continue;
		seen.add(key);
		ordered.push(item);
		if (prev.has(key)) kept.push(item);
		else added.push(item);
	}

	const removed: MarkerKey[] = [];
	for (const key of prev) {
		if (!seen.has(key)) removed.push(key);
	}

	return { added, kept, removed, ordered };
}

/**
 * The parts of a photo that are baked into the marker's icon HTML. When this
 * changes between publishes the icon has to be rebuilt; everything else that
 * can change (position, bearing-diff colour, grayed state, selection) is
 * patched on the existing element without touching its structure.
 */
export function iconSignature(photo: {
	id: string;
	bearing?: number;
	featured?: boolean;
	filtered?: boolean;
	is_placeholder?: boolean;
	// PhotoData.source is a Source object from the worker, or just its id.
	source?: string | { id?: string; color?: string } | null;
}): string {
	const source = typeof photo.source === 'string' ? { id: photo.source } : photo.source;
	return [
		photo.id,
		photo.bearing ?? 0,
		photo.featured ? 1 : 0,
		photo.filtered ? 1 : 0,
		photo.is_placeholder ? 1 : 0,
		source?.id ?? '',
		source?.color ?? ''
	].join('|');
}
