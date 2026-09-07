import { describe, it, expect, vi } from 'vitest';

// Formatter-only tests; the module's fetch side lives behind $lib/http.
vi.mock('$lib/http', () => ({ http: { get: vi.fn() } }));

import {
	formatAperture,
	formatIso,
	formatShutter,
	formatFrames,
	formatFocalLength,
	formatCamera
} from './photoExif';

describe('formatShutter', () => {
	it('renders the conventional fraction below a quarter second', () => {
		expect(formatShutter(0.002)).toBe('1/500 s');
		expect(formatShutter(0.004)).toBe('1/250 s'); // 249.999… snaps to 250
		expect(formatShutter(0.25)).toBe('1/4 s');
	});

	it('renders decimals from a quarter second up (exiftool rule)', () => {
		expect(formatShutter(0.4)).toBe('0.4 s');
		expect(formatShutter(1)).toBe('1 s');
		expect(formatShutter(2.5)).toBe('2.5 s');
	});

	it('renders a bracket range with the unit once', () => {
		expect(formatShutter(undefined, [0.0005, 0.008])).toBe('1/2000–1/125 s');
		expect(formatShutter(undefined, [0.002, 0.5])).toBe('1/500–0.5 s');
	});

	it('marks positions that disagree', () => {
		expect(formatShutter(undefined, [0.0005, 0.008], true)).toBe('1/2000–1/125 s + other');
		expect(formatShutter(0.002, undefined, true)).toBe('1/500 s + other');
	});

	it('is null without a usable value', () => {
		expect(formatShutter(undefined)).toBeNull();
		expect(formatShutter(0)).toBeNull();
		expect(formatShutter(undefined, [0, 0.008])).toBeNull();
	});
});

describe('formatAperture / formatIso', () => {
	it('render scalars as before', () => {
		expect(formatAperture(9.5)).toBe('ƒ/9.5');
		expect(formatIso(400)).toBe('ISO 400');
		expect(formatAperture(undefined)).toBeNull();
		expect(formatIso(undefined)).toBeNull();
	});

	it('render ranges and the mixed marker', () => {
		expect(formatAperture(undefined, [8, 11])).toBe('ƒ/8–11');
		expect(formatIso(undefined, [100, 800])).toBe('ISO 100–800');
		expect(formatIso(400, undefined, true)).toBe('ISO 400 + other');
		expect(formatAperture(undefined, [8, 11], true)).toBe('ƒ/8–11 + other');
	});
});

describe('formatFrames', () => {
	it('shows a stack count, with positions only when they hold brackets', () => {
		expect(formatFrames(6)).toBe('6');
		expect(formatFrames(36, 12)).toBe('36 (12 positions)');
		// The prod panos so far: one frame per position.
		expect(formatFrames(94, 94)).toBe('94');
	});

	it('is null for a single frame or nothing', () => {
		expect(formatFrames(1)).toBeNull();
		expect(formatFrames(undefined)).toBeNull();
		expect(formatFrames(1, 1)).toBeNull();
	});
});

describe('unchanged formatters', () => {
	it('focal length with 35mm equivalent only when it differs', () => {
		expect(formatFocalLength({ focal_length: 24, focal_length_35mm: 36 })).toBe('24 mm (36 mm eq.)');
		expect(formatFocalLength({ focal_length: 170, focal_length_35mm: 170 })).toBe('170 mm');
		expect(formatFocalLength({})).toBeNull();
	});

	it('camera avoids repeating the make', () => {
		expect(formatCamera('Canon', 'Canon EOS R6')).toBe('Canon EOS R6');
		expect(formatCamera('Sony', 'ILCE-7M3')).toBe('Sony ILCE-7M3');
	});
});
