/**
 * Utility functions for handling datetime strings across platforms.
 *
 * Display convention (site-wide): ISO 8601 order, 24-hour clock —
 * "2026-08-24 15:45:12". Deliberately locale-independent so web and the
 * Android WebView render identically and tests can assert exact strings.
 * Viewer-zone formatters convert the stored UTC instant to the device's
 * timezone; surfaces that need the zone spelled out use formatDateTimeZoned
 * or pair the value with viewerZoneInfo (e.g. the photo info overlay).
 */

/** Anything that denotes an absolute instant somewhere in the app. */
export type InstantInput = string | number | Date | null | undefined;

/**
 * Normalize Python datetime string to JavaScript Date-compatible format
 *
 * Python datetime strings often include microseconds (6 digits after decimal)
 * but JavaScript Date only supports milliseconds (3 digits after decimal).
 *
 * @param dateTimeString - Python datetime string (e.g., "2025-09-12T15:42:32.392433Z")
 * @returns Normalized datetime string (e.g., "2025-09-12T15:42:32.392Z")
 */
export function normalizePythonDateTime(dateTimeString: string): string {
    // Convert from microseconds (6 digits) to milliseconds (3 digits)
    // Regex explanation:
    // (\.\d{3}) - capture first 3 digits after decimal point
    // \d{3}     - match and remove the next 3 digits (microseconds to remove)
    // Z?$       - optional Z at end of string
    return dateTimeString.replace(/(\.\d{3})\d{3}Z?$/, '$1Z');
}

/**
 * Parse a Python datetime string into a JavaScript Date object
 *
 * @param dateTimeString - Python datetime string
 * @returns JavaScript Date object, or null if parsing fails
 */
export function parsePythonDateTime(dateTimeString: string): Date | null {
    try {
        const normalized = normalizePythonDateTime(dateTimeString);
        const date = new Date(normalized);

        // Check if the date is valid
        if (isNaN(date.getTime())) {
            return null;
        }

        return date;
    } catch (error) {
        console.error('Error parsing Python datetime:', error);
        return null;
    }
}

// Backend timestamps are UTC. Most endpoints stamp the 'Z' explicitly
// (common/utc.py format_utc), but a few emit naive .isoformat() strings —
// which new Date() would read in the viewer's zone, silently shifting the
// instant by the viewer's offset. Treat an offset-less string as UTC.
const TZ_SUFFIX_RE = /(?:Z|[+-]\d\d:?\d\d)$/i;

/**
 * Parse any of the app's instant shapes into a Date: ISO strings (with or
 * without microseconds; offset-less strings are treated as UTC), epoch ms
 * numbers (Panoramax), or a Date passed through.
 *
 * @returns Date, or null when the value is empty or unparseable
 */
export function parseInstant(value: InstantInput): Date | null {
    if (value === null || value === undefined || value === '') return null;
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
    if (typeof value === 'number') {
        const date = new Date(value);
        return isNaN(date.getTime()) ? null : date;
    }
    const normalized = normalizePythonDateTime(value);
    const date = new Date(TZ_SUFFIX_RE.test(normalized) ? normalized : normalized + 'Z');
    return isNaN(date.getTime()) ? null : date;
}

function pad2(n: number): string {
    return String(n).padStart(2, '0');
}

/** "2026-08-24" / "2026-08-24 15:45[:12]" from a Date, in UTC or viewer zone. */
export function isoDate(d: Date, utc = false): string {
    const y = utc ? d.getUTCFullYear() : d.getFullYear();
    const m = (utc ? d.getUTCMonth() : d.getMonth()) + 1;
    const day = utc ? d.getUTCDate() : d.getDate();
    return `${y}-${pad2(m)}-${pad2(day)}`;
}

export function isoTimeSec(d: Date, utc = false): string {
    const hh = utc ? d.getUTCHours() : d.getHours();
    const mm = utc ? d.getUTCMinutes() : d.getMinutes();
    const ss = utc ? d.getUTCSeconds() : d.getSeconds();
    return `${pad2(hh)}:${pad2(mm)}:${pad2(ss)}`;
}

export function isoDateTimeSec(d: Date, utc = false): string {
    return `${isoDate(d, utc)} ${isoTimeSec(d, utc)}`;
}

export function isoDateTimeMin(d: Date, utc = false): string {
    const hh = utc ? d.getUTCHours() : d.getHours();
    const mm = utc ? d.getUTCMinutes() : d.getMinutes();
    return `${isoDate(d, utc)} ${pad2(hh)}:${pad2(mm)}`;
}

// The site-wide display vocabulary. All convert to the VIEWER's timezone
// (except formatUtcDateTime) and return '' for empty input, or the raw input
// stringified when unparseable — so templates degrade to showing the value.
function displayed(value: InstantInput, render: (d: Date) => string): string {
    if (value === null || value === undefined || value === '') return '';
    const d = parseInstant(value);
    return d ? render(d) : String(value);
}

/** "2026-08-24" in the viewer's timezone. */
export function formatDate(value: InstantInput): string {
    return displayed(value, d => isoDate(d));
}

/** "2026-08-24 15:45" in the viewer's timezone. */
export function formatDateTime(value: InstantInput): string {
    return displayed(value, d => isoDateTimeMin(d));
}

/** "2026-08-24 15:45:12" in the viewer's timezone. */
export function formatDateTimeSec(value: InstantInput): string {
    return displayed(value, d => isoDateTimeSec(d));
}

/** "15:45:12" in the viewer's timezone (clocks, logs, debug readouts). */
export function formatTimeSec(value: InstantInput): string {
    return displayed(value, d => isoTimeSec(d));
}

/**
 * "2026-08-24 15:45:12 UTC+02:00" — viewer-zone time with the conversion
 * target made explicit. For surfaces that show a bare timestamp with no
 * accompanying zone affordance (e.g. the photo detail page).
 */
export function formatDateTimeZoned(value: InstantInput): string {
    return displayed(value, d => `${isoDateTimeSec(d)} ${viewerUtcOffset(d)}`);
}

/**
 * Format a datetime as ISO date with 24-hour UTC time: "2026-07-13 17:16:08
 * UTC". Deliberately locale- and timezone-independent so admin logs read the
 * same for every operator regardless of browser settings.
 *
 * @param value - Python/ISO datetime string (or epoch ms / Date)
 * @returns Formatted string, or '' for empty input (or the raw input if unparseable)
 */
export function formatUtcDateTime(value: InstantInput): string {
    return displayed(value, d => `${isoDateTimeSec(d, true)} UTC`);
}

/**
 * The viewer's UTC offset at the given instant (so DST is accounted for),
 * e.g. "UTC+02:00". getTimezoneOffset is minutes *behind* UTC (UTC+2 → -120).
 */
export function viewerUtcOffset(d: Date): string {
    const offsetMin = -d.getTimezoneOffset();
    const absMin = Math.abs(offsetMin);
    return `UTC${offsetMin < 0 ? '-' : '+'}${pad2(Math.floor(absMin / 60))}:${pad2(absMin % 60)}`;
}

/**
 * The viewer's zone for the given instant: offset ("UTC+02:00") plus IANA
 * name ("Europe/Prague") when the environment exposes it.
 */
export function viewerZoneInfo(value: InstantInput): { offset: string; zone: string | null } | null {
    const d = parseInstant(value);
    if (!d) return null;
    let zone: string | null = null;
    try {
        zone = Intl.DateTimeFormat().resolvedOptions().timeZone ?? null;
    } catch {
        // Intl may be crippled in odd WebViews; offset alone is still correct.
    }
    return { offset: viewerUtcOffset(d), zone };
}
