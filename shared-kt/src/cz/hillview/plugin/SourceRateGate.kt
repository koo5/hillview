package cz.hillview.plugin

import java.util.concurrent.ConcurrentHashMap

/**
 * The per-source write gate for the tracking tables — one instance per table,
 * held by [GeoTrackingManager].
 *
 * This was a single `lastStorageTime` field per table, which made every stream
 * compete for one 10 ms slot: a 1 Hz `gps-kalman` bearing could lose it to the
 * ~10 Hz sensor stream and be dropped before the row ever reached the
 * database. Worse, the clock advanced on REJECTION as well as acceptance, so
 * any stream arriving faster than the interval starved every writer
 * indefinitely.
 *
 * Per-source, the gate is a floor against one runaway source rather than a
 * coordination mechanism between them: the streams are already rate-limited
 * upstream (EnhancedSensorService at 10 Hz, fixes at ~1 Hz).
 *
 * [clock] is injectable only so the rules above can be asserted without
 * sleeping — production always runs on the wall clock.
 */
internal class SourceRateGate(
    private val intervalMs: Long,
    private val clock: () -> Long = System::currentTimeMillis,
) {
    private val lastAccepted = ConcurrentHashMap<Int, Long>()

    /**
     * True when [sourceId] may store a row now, claiming its slot in the same
     * step. compute() is atomic per key, so two threads writing one source
     * can't both pass; and only an ACCEPTED sample moves that source's clock
     * forward, so a fast stream can no longer starve itself.
     */
    fun allow(sourceId: Int): Boolean {
        val currentTime = clock()
        var ok = false
        lastAccepted.compute(sourceId) { _, last ->
            if (last == null || currentTime - last >= intervalMs) {
                ok = true
                currentTime
            } else {
                last
            }
        }
        return ok
    }
}
