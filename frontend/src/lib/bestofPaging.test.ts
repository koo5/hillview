import { describe, it, expect } from 'vitest';
import { parsePageParam } from './bestofPaging';

describe('parsePageParam', () => {
	it('reads a page number', () => {
		expect(parsePageParam('3')).toBe(3);
	});

	it('falls back to page 1 for anything unusable', () => {
		// A crawler or a typo can hand us anything; none of it may reach the API
		// as a page that would offset into negative space.
		for (const bad of [null, '', 'abc', '0', '-2', 'NaN', 'Infinity']) {
			expect(parsePageParam(bad)).toBe(1);
		}
	});

	it('floors a fractional page', () => {
		expect(parsePageParam('2.7')).toBe(2);
	});
});
