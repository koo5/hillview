import { describe, it, expect } from 'vitest';
import { computePhotoInFront, toTableSource, kotlinOwnsSource } from './mapState';

/**
 * The boundary where the app's own bearing/location source names become the
 * tracking tables' vocabulary — see docs/geo-election-test-todo.md item 5.
 *
 * Two rules meet here, and both are load-bearing for the election:
 *  - `source` is coarse and EXACT (android | gps-kalman | manual); the fine
 *    name survives as `detail`. "Re-query the elected source" is then a plain
 *    equality, with no lookup table.
 *  - `kotlinOwnsSource` decides who WRITES the row. Echoing a source Kotlin
 *    already writes files a second row for the same sample.
 */
describe('toTableSource', () => {
	it('collapses the app\'s own bearing sources to manual, keeping the name as detail', () => {
		// These are bearingState sources, which stay fine-grained in the UI and
		// in the EXIF bearing_source — they coarsen only on the way to a row.
		for (const source of ['map', 'arrow_drag', 'url', 'featured', 'photo_navigation']) {
			expect(toTableSource(source)).toEqual({ source: 'manual', detail: source });
		}
	});

	it('keeps gps-kalman as itself — it is separately elect-able (car mode)', () => {
		expect(toTableSource('gps-kalman')).toEqual({ source: 'gps-kalman', detail: '' });
	});

	it('elects a compass reading as android whichever API produced it', () => {
		// currentCompassHeading (compass.svelte.ts) builds these names as
		// `${compassData.source}-compass-${true|magnetic}`. The '-compass-'
		// test mirrors that construction and the two must move together.
		expect(toTableSource('android-compass-true')).toEqual({
			source: 'android',
			detail: 'android-compass-true',
		});
		// The WEB DeviceOrientation fallback. It reaches the tables for real —
		// startCompassInternal drops to it when the native sensor won't start —
		// and it is still the phone's compass: the user elects "walking
		// compass", not an API. Labelling it `manual` would corrupt the
		// election, and it is the one case where the source name alone does
		// not say "android".
		expect(toTableSource('web-absolute-compass-true')).toEqual({
			source: 'android',
			detail: 'web-absolute-compass-true',
		});
		expect(toTableSource('web-magnetic-compass-magnetic')).toEqual({
			source: 'android',
			detail: 'web-magnetic-compass-magnetic',
		});
	});

	it('only ever answers with the elect-able vocabulary', () => {
		const vocabulary = ['android', 'gps-kalman', 'manual'];
		for (const source of [
			'map', 'arrow_drag', 'url', 'featured', 'photo_navigation', 'gps-kalman',
			'android-compass-true', 'web-absolute-compass-true', 'tauri-compass-magnetic',
			'', 'something-nobody-has-written-yet',
		]) {
			expect(vocabulary).toContain(toTableSource(source).source);
		}
	});
});

describe('computePhotoInFront', () => {
	const p = (uid: string, bearing: number, extra: Record<string, unknown> = {}) => ({ uid, bearing, ...extra });

	it('picks the nearest bearing, uid as the tiebreaker', () => {
		const photos = [p('b', 90), p('a', 90), p('c', 180)];
		expect(computePhotoInFront(photos, { bearing: 92 })?.uid).toBe('a');
	});

	it('a chosen photo wins only while the view looks straight at it', () => {
		const photos = [p('chosen', 90), p('other', 100)];
		expect(computePhotoInFront(photos, { bearing: 90, photoUid: 'chosen' })?.uid).toBe('chosen');
		// view moved off it → nearest bearing again
		expect(computePhotoInFront(photos, { bearing: 100, photoUid: 'chosen' })?.uid).toBe('other');
	});

	it('a chosen heading-less photo wins wherever the view points — the uid IS the selection', () => {
		const photos = [p('grey', 0, { has_bearing: false }), p('other', 100)];
		expect(computePhotoInFront(photos, { bearing: 100, photoUid: 'grey' })?.uid).toBe('grey');
	});

	it('without a choice, plain nearest-bearing applies — has_bearing gives no priority', () => {
		// (A heading-less photo normally is not even in range without a pick;
		// if it is, it competes by its wire bearing like before the flag.)
		const photos = [p('grey', 0, { has_bearing: false }), p('east', 90)];
		expect(computePhotoInFront(photos, { bearing: 2 })?.uid).toBe('grey');
		expect(computePhotoInFront(photos, { bearing: 80 })?.uid).toBe('east');
	});
});

describe('kotlinOwnsSource', () => {
	it('covers the native sensor stream and the composed car heading', () => {
		// gps-kalman was a duplicate-row bug: Kotlin writes that row at the
		// fix's own location.time, while an echo from here is stamped
		// Date.now() at event delivery — so the composite key faithfully keeps
		// BOTH instead of collapsing them.
		expect(kotlinOwnsSource('android')).toBe(true);
		expect(kotlinOwnsSource('android-compass-true')).toBe(true);
		expect(kotlinOwnsSource('gps-kalman')).toBe(true);
	});

	it('leaves the frontend-owned sources to the frontend', () => {
		for (const source of ['map', 'arrow_drag', 'url', 'featured', 'photo_navigation']) {
			expect(kotlinOwnsSource(source)).toBe(false);
		}
	});

	it('does not claim the web compass fallback, which no native stream records', () => {
		// It elects AS android (above) but is written from here — the value
		// never crossed the JS bridge, so there is no Kotlin-side row to
		// duplicate. This asymmetry is deliberate; is_sensor_bearing_source()
		// in src-tauri/src/device_photos.rs mirrors it.
		expect(kotlinOwnsSource('web-absolute-compass-true')).toBe(false);
		expect(kotlinOwnsSource('web-magnetic-compass-magnetic')).toBe(false);
	});

	it('matches by prefix, not by substring', () => {
		// The substring sweep this replaced matched anything CONTAINING
		// "compass"/"sensor"/"tauri"; the vocabulary is exact now.
		expect(kotlinOwnsSource('manual-android')).toBe(false);
		expect(kotlinOwnsSource('not-gps-kalman')).toBe(false);
	});
});
