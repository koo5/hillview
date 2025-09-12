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