import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { pendingLoads, trackLoad } from './pageLoading';

describe('trackLoad', () => {
	it('counts a load while it runs and releases it after', async () => {
		let seenDuring = -1;
		const result = await trackLoad(async () => {
			seenDuring = get(pendingLoads);
			return 'done';
		});
		expect(seenDuring).toBe(1);
		expect(result).toBe('done');
		expect(get(pendingLoads)).toBe(0);
	});

	it('releases the count when the load throws', async () => {
		await expect(
			trackLoad(async () => {
				throw new Error('network');
			})
		).rejects.toThrow('network');
		// A page that fails its viewer-correcting fetch is finished loading too —
		// leaking the count here would leave the app permanently "not ready".
		expect(get(pendingLoads)).toBe(0);
	});

	it('holds until the last of several overlapping loads finishes', async () => {
		let releaseA: () => void = () => {};
		let releaseB: () => void = () => {};
		const a = trackLoad(() => new Promise<void>((r) => (releaseA = r)));
		const b = trackLoad(() => new Promise<void>((r) => (releaseB = r)));
		expect(get(pendingLoads)).toBe(2);

		releaseA();
		await a;
		expect(get(pendingLoads)).toBe(1);

		releaseB();
		await b;
		expect(get(pendingLoads)).toBe(0);
	});
});
