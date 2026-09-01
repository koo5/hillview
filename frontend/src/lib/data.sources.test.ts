/**
 * Source defaults and the capture-mode source swap in data.svelte.ts.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock(import('$lib/tauri'), async (importOriginal) => ({
	...(await importOriginal()),
	TAURI: false,
	BROWSER: true,
	TAURI_MOBILE: false
}));
vi.mock('$app/environment', () => ({ browser: true, dev: true }));

import { sources, onAppActivityChange, defaultSourceEnabled } from './data.svelte';

const enabledIds = () => get(sources).filter(s => s.enabled).map(s => s.id).sort();
const setEnabled = (ids: string[]) =>
	sources.update(srcs => srcs.map(s => ({ ...s, enabled: ids.includes(s.id) })));

describe('source defaults', () => {
	it('panoramax is on by default, mapillary off', () => {
		expect(defaultSourceEnabled('panoramax')).toBe(true);
		expect(defaultSourceEnabled('hillview')).toBe(true);
		expect(defaultSourceEnabled('mapillary')).toBe(false);
	});
});

describe('onAppActivityChange', () => {
	beforeEach(() => {
		setEnabled(['hillview', 'panoramax']);
		onAppActivityChange('view'); // clear any remembered set from a previous test
		setEnabled(['hillview', 'panoramax']);
	});

	it('capture mode narrows to the device source (none on web) and exit restores what was on', () => {
		setEnabled(['hillview', 'mapillary']);
		onAppActivityChange('capture');
		expect(enabledIds()).toEqual([]);

		onAppActivityChange('view');
		expect(enabledIds()).toEqual(['hillview', 'mapillary']);
	});

	it('a non-capture activity change leaves the persisted choice alone', () => {
		setEnabled(['mapillary']);
		onAppActivityChange('view');   // startup / leaving the lines editor
		expect(enabledIds()).toEqual(['mapillary']);
		onAppActivityChange('lines');
		expect(enabledIds()).toEqual(['mapillary']);
	});

	it('a device-only set with nothing remembered (killed mid-capture) falls back to the defaults', () => {
		setEnabled([]);
		onAppActivityChange('view');
		expect(enabledIds()).toEqual(['hillview', 'panoramax']);
	});
});
