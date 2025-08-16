/**
 * EventSource utility functions
 */

/**
 * Converts EventSource readyState numeric value to human-readable string
 * @param readyState - The numeric readyState value from EventSource
 * @returns Human-readable string representation of the state
 */
export function verbalizeEventSourceReadyState(readyState: number): string {
    switch (readyState) {
        case EventSource.CONNECTING:
            return 'CONNECTING(0)';
        case EventSource.OPEN:
            return 'OPEN(1)';
        case EventSource.CLOSED:
            return 'CLOSED(2)';
        default:
            return `UNKNOWN(${readyState})`;
    }
}