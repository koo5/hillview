import { describe, it, expect } from 'vitest';
import { getCapturedAtDetails } from './photoUtils';
import type { PhotoData } from './types/photoTypes';

describe('captured_at timezone details', () => {
	it('derives UTC details from an ISO-Z string (hillview/mapillary shape)', () => {
		const photo = { captured_at: '2026-08-24T13:45:12.000000Z' } as unknown as PhotoData;
		const details = getCapturedAtDetails(photo);
		expect(details).not.toBeNull();
		expect(details!.utc).toBe('2026-08-24 13:45:12');
		expect(details!.offset).toMatch(/^UTC[+-]\d{2}:\d{2}$/);
	});

	it('derives UTC details from epoch ms (panoramax shape)', () => {
		const photo = { captured_at: Date.UTC(2026, 7, 24, 13, 45, 12) } as unknown as PhotoData;
		expect(getCapturedAtDetails(photo)!.utc).toBe('2026-08-24 13:45:12');
	});

	it('returns null for missing or unparseable captured_at', () => {
		expect(getCapturedAtDetails(null)).toBeNull();
		expect(getCapturedAtDetails({} as PhotoData)).toBeNull();
		expect(getCapturedAtDetails({ captured_at: 'garbage' } as unknown as PhotoData)).toBeNull();
	});
});
