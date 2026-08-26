import { describe, it, expect } from 'vitest';
import {
	parseInstant,
	isoDateTimeSec,
	formatUtcDateTime,
	formatDate,
	formatDateTime,
	formatDateTimeSec,
	viewerUtcOffset
} from './dateUtils';

// Only the UTC-rendering paths assert exact strings — viewer-zone output
// depends on the machine's TZ, so those tests check shape, not values.

describe('parseInstant', () => {
	it('parses ISO-Z strings, including python microseconds', () => {
		expect(parseInstant('2026-06-21T13:29:13Z')!.getTime()).toBe(Date.UTC(2026, 5, 21, 13, 29, 13));
		expect(parseInstant('2026-06-21T13:29:13.000000Z')!.getTime()).toBe(
			Date.UTC(2026, 5, 21, 13, 29, 13)
		);
	});

	it('treats offset-less strings as UTC (naive .isoformat() endpoints)', () => {
		expect(parseInstant('2026-06-21T13:29:13')!.getTime()).toBe(Date.UTC(2026, 5, 21, 13, 29, 13));
	});

	it('respects explicit offsets', () => {
		expect(parseInstant('2026-06-21T13:29:13+02:00')!.getTime()).toBe(
			Date.UTC(2026, 5, 21, 11, 29, 13)
		);
	});

	it('accepts epoch ms and Date passthrough', () => {
		const ms = Date.UTC(2026, 7, 24, 13, 45, 12);
		expect(parseInstant(ms)!.getTime()).toBe(ms);
		expect(parseInstant(new Date(ms))!.getTime()).toBe(ms);
	});

	it('returns null for empty or garbage input', () => {
		expect(parseInstant(null)).toBeNull();
		expect(parseInstant(undefined)).toBeNull();
		expect(parseInstant('')).toBeNull();
		expect(parseInstant('garbage')).toBeNull();
	});
});

describe('ISO display formatting', () => {
	it('renders UTC date-times in ISO order, 24-h', () => {
		const d = parseInstant('2026-08-24T13:45:12Z')!;
		expect(isoDateTimeSec(d, true)).toBe('2026-08-24 13:45:12');
		expect(formatUtcDateTime('2026-08-24T13:45:12.392433Z')).toBe('2026-08-24 13:45:12 UTC');
		expect(isoDateTimeSec(parseInstant('2026-01-03T04:05:06Z')!, true)).toBe('2026-01-03 04:05:06');
	});

	it('returns empty string for empty input, raw input when unparseable', () => {
		expect(formatUtcDateTime(null)).toBe('');
		expect(formatDateTime(undefined)).toBe('');
		expect(formatDate('garbage')).toBe('garbage');
	});

	it('viewer-zone formatters produce the ISO shape', () => {
		expect(formatDate('2026-08-24T13:45:12Z')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
		expect(formatDateTime('2026-08-24T13:45:12Z')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
		expect(formatDateTimeSec('2026-08-24T13:45:12Z')).toMatch(
			/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/
		);
	});

	it('viewerUtcOffset uses the offset at the given instant', () => {
		expect(viewerUtcOffset(new Date('2026-08-24T13:45:12Z'))).toMatch(/^UTC[+-]\d{2}:\d{2}$/);
	});
});
