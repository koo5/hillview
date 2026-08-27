import { describe, it, expect } from 'vitest';
import { diffByKey, markerKey, iconSignature } from './markerDiff';

const p = (id: string, uid?: string) => ({ id, uid });

describe('diffByKey', () => {
	it('splits the next set into added / kept and lists what left', () => {
		const d = diffByKey(['a', 'b'], [p('b'), p('c')], markerKey);
		expect(d.added.map(markerKey)).toEqual(['c']);
		expect(d.kept.map(markerKey)).toEqual(['b']);
		expect(d.removed).toEqual(['a']);
		expect(d.ordered.map(markerKey)).toEqual(['b', 'c']);
	});

	it('an empty previous set means everything is added', () => {
		const d = diffByKey([], [p('a'), p('b')], markerKey);
		expect(d.added).toHaveLength(2);
		expect(d.kept).toHaveLength(0);
		expect(d.removed).toHaveLength(0);
	});

	it('an empty next set removes everything', () => {
		const d = diffByKey(['a', 'b'], [], markerKey);
		expect(d.removed.sort()).toEqual(['a', 'b']);
		expect(d.ordered).toEqual([]);
	});

	it('drops duplicate keys in next, first one wins, and never double-counts them', () => {
		const first = p('x');
		const d = diffByKey([], [first, p('x'), p('y')], markerKey);
		expect(d.ordered).toEqual([first, p('y')]);
		expect(d.added).toEqual([first, p('y')]);
	});

	it('preserves next order in `ordered` regardless of previous order', () => {
		const d = diffByKey(['c', 'a', 'b'], [p('b'), p('a'), p('c')], markerKey);
		expect(d.ordered.map(markerKey)).toEqual(['b', 'a', 'c']);
		expect(d.kept.map(markerKey)).toEqual(['b', 'a', 'c']);
	});
});

describe('markerKey', () => {
	it('prefers the source-qualified uid so the same id from two sources stays distinct', () => {
		expect(markerKey({ id: '1', uid: 'hillview-1' })).toBe('hillview-1');
		expect(markerKey({ id: '1', uid: 'mapillary-1' })).toBe('mapillary-1');
		expect(markerKey({ id: '1' })).toBe('1');
	});
});

describe('iconSignature', () => {
	const base = { id: 'a', bearing: 90, featured: false, filtered: false, source: { id: 'hillview', color: '#0f0' } };

	it('is stable for the fields that are only patched in place', () => {
		const sig = iconSignature(base);
		expect(iconSignature({ ...base, bearing_color: '#f00', abs_bearing_diff: 12, coord: { lat: 1, lng: 2 } } as any)).toBe(sig);
	});

	it('accepts a bare source id as well as a Source object', () => {
		expect(iconSignature({ ...base, source: 'hillview' })).toBe(iconSignature({ ...base, source: { id: 'hillview' } }));
	});

	it('changes when a baked-in field changes', () => {
		const sig = iconSignature(base);
		expect(iconSignature({ ...base, bearing: 91 })).not.toBe(sig);
		expect(iconSignature({ ...base, featured: true })).not.toBe(sig);
		expect(iconSignature({ ...base, filtered: true })).not.toBe(sig);
		expect(iconSignature({ ...base, is_placeholder: true })).not.toBe(sig);
		expect(iconSignature({ ...base, source: { id: 'mapillary', color: '#0f0' } })).not.toBe(sig);
	});
});
