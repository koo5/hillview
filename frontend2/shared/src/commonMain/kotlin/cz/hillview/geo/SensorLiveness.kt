package cz.hillview.geo

/**
 * Is the attitude sensor delivering events that say nothing?
 *
 * There are two ways a sensor registration dies. The loud one is silence,
 * and the watchdog has always caught it. The quiet one keeps delivering at
 * full rate while repeating a single frozen sample — every consumer
 * downstream stays healthy, the smoothing converges on the frozen value,
 * the elected bearing tracks it faithfully, and the heading ends up
 * answering to nothing but the device-orientation remap. From the outside
 * that is a compass alternating between a couple of values depending on how
 * the phone is held.
 *
 * Repetition alone cannot be the test: a phone on a table legitimately
 * repeats. What makes it a fault is repetition WHILE THE PHONE MOVED, and
 * the evidence for movement has to come from outside the suspect
 * registration — hence the device-orientation class, which
 * OrientationEventListener derives from its own accelerometer listener
 * inside the framework and which therefore keeps working when ours is the
 * dead one. A class change is a ≥45° turn: no real sensor sits through one
 * without its vector moving.
 *
 * All times are elapsed-realtime milliseconds; 0 means "never happened".
 */
fun sensorLooksStuck(
    nowMs: Long,
    /** When an event last ARRIVED. Zero = nothing ever has; that is silence, not stuckness. */
    rawEventAtMs: Long,
    /** When a sample last carried a different value than the one before. */
    valueChangeAtMs: Long,
    /** When the device-orientation class last changed. */
    orientationChangeAtMs: Long,
    /** How long a repeat has to last before it counts (backs off on retries). */
    stuckLimitMs: Long,
): Boolean {
    if (rawEventAtMs == 0L || valueChangeAtMs == 0L) return false
    // Zero is "never turned", which is the ABSENCE of evidence — and a
    // restart needs evidence. (A phone that has been flat since launch
    // reports no class change at all, and would otherwise be restarted for
    // lying still, which is the one thing this must not do.)
    if (orientationChangeAtMs == 0L) return false
    if (nowMs - valueChangeAtMs <= stuckLimitMs) return false
    // The turn has to be NEWER than the last time the value moved. A turn
    // that happened before it proves nothing: the sample moved afterwards.
    return orientationChangeAtMs > valueChangeAtMs
}
