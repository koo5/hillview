import { describe, it, expect } from 'vitest';
import { findCoords, firstCoords, isCoordsOnly } from './coordParser';

// Cases mirror the Python twin's suite: enrich/api/app/tests/test_parser.py
describe('firstCoords', () => {
	it('parses "lat N, lon E" with hemisphere letters', () => {
		expect(firstCoords('50.732N, 15.008E')).toEqual({
			lat: 50.732,
			lon: 15.008,
			text: '50.732N, 15.008E',
			index: 0,
		});
	});

	it('parses a plain comma-separated pair', () => {
		const c = firstCoords('50.732, 15.008');
		expect(c?.lat).toBe(50.732);
		expect(c?.lon).toBe(15.008);
	});

	it('parses a whitespace-separated pair', () => {
		const c = firstCoords('50.100N 14.500E');
		expect(c?.lat).toBe(50.1);
		expect(c?.lon).toBe(14.5);
	});

	it('parses Czech decimal-comma pairs', () => {
		const c = firstCoords('50,0620061, 14,8864855');
		expect(c?.lat).toBe(50.0620061);
		expect(c?.lon).toBe(14.8864855);
	});

	it('negates on S/W hemisphere letters', () => {
		expect(firstCoords('33.8568S, 151.2153E')).toMatchObject({ lat: -33.8568, lon: 151.2153 });
		expect(firstCoords('40.7128N, 74.0060W')).toMatchObject({ lat: 40.7128, lon: -74.006 });
	});

	it('reports the offset of an embedded pair', () => {
		const c = firstCoords('Ještěd 50.732N, 15.008E');
		expect(c?.index).toBe(7);
		expect(c?.text).toBe('50.732N, 15.008E');
	});

	it('requires 3+ decimal places (prose numbers do not match)', () => {
		expect(firstCoords('50.73, 15.00')).toBeNull();
		expect(firstCoords('built 1938, 1500 m')).toBeNull();
	});
});

describe('findCoords', () => {
	it('finds every pair in a text', () => {
		const all = findCoords('50.732N, 15.008E and 49.5504N, 18.4471E');
		expect(all).toHaveLength(2);
		expect(all[1]).toMatchObject({ lat: 49.5504, lon: 18.4471, index: 21 });
	});

	it('returns empty array when nothing matches', () => {
		expect(findCoords('no coordinates here')).toEqual([]);
	});
});

describe('isCoordsOnly', () => {
	it('accepts a bare pair', () => {
		expect(isCoordsOnly('50.732N, 15.008E')).toBe(true);
		expect(isCoordsOnly('50,0620061, 14,8864855')).toBe(true);
	});

	it('rejects a pair embedded after a name', () => {
		expect(isCoordsOnly('Ještěd 50.732N, 15.008E')).toBe(false);
	});

	it('rejects empty and prose strings', () => {
		expect(isCoordsOnly('')).toBe(false);
		expect(isCoordsOnly('Petřín')).toBe(false);
	});
});
