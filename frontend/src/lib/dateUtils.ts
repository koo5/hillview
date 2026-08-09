/**
 * Utility functions for handling datetime strings across platforms
 */

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

/**
 * Format a datetime as fixed European day-month-year with 24-hour UTC time:
 * "13-07-2026 17:16:08 UTC". Deliberately locale- and timezone-independent so
 * admin logs read the same for every operator regardless of browser settings.
 *
 * @param dateTimeString - Python/ISO datetime string
 * @returns Formatted string, or '' for empty input (or the raw input if unparseable)
 */
export function formatUtcDateTime(dateTimeString: string | null | undefined): string {
    if (!dateTimeString) return '';
    const d = parsePythonDateTime(dateTimeString);
    if (!d) return dateTimeString;
    const pad = (n: number) => String(n).padStart(2, '0');
    const date = `${pad(d.getUTCDate())}-${pad(d.getUTCMonth() + 1)}-${d.getUTCFullYear()}`;
    const time = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
    return `${date} ${time} UTC`;
}