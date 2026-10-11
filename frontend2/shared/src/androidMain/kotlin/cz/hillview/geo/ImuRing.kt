package cz.hillview.geo

import cz.hillview.plugin.ImuSampleEntity

/**
 * The IMU ring buffer — raw accelerometer and gyroscope at sensor rate,
 * held in MEMORY and persisted only around a shutter.
 *
 * Continuous persistence was rejected on arithmetic: two hours at 100 Hz is
 * ~720 000 rows, against ~100 per photo for a one-second window. So the
 * buffer is a fixed-size circular array sized to the widest window anyone
 * will ask for, and `GeoEngine.persistImuWindow` copies a slice of it out.
 *
 * Its own file and `internal` rather than private inside the engine, so the
 * wraparound and the per-millisecond sequencing — which are real logic and
 * were briefly untestable — have a host test (`ImuRingTest`).
 *
 * Deliberately NOT published as a flow. Everything else the engine measures
 * reaches the app through the one state, but a 100 Hz buffer is not
 * user-facing state and pushing it through recomposition would be absurd —
 * a hundred samples re-emitted a hundred times a second. The capture path
 * ASKS, once, at the shutter.
 */
internal class ImuRing(val capacity: Int) {
    private val timestamp = LongArray(capacity)
    private val elapsedNanos = LongArray(capacity)
    // An Int, not the String the entity stores: at a few hundred hertz across
    // two sensors this array is scanned constantly, and a reference per slot
    // plus a string compare per sample is a cost with nothing to show for it.
    private val kind = IntArray(capacity) { KIND_NONE }
    private val x = FloatArray(capacity)
    private val y = FloatArray(capacity)
    private val z = FloatArray(capacity)
    private var writeAt = 0
    private var filled = 0

    @Synchronized
    fun add(atMs: Long, nanos: Long, k: Int, vx: Float, vy: Float, vz: Float) {
        timestamp[writeAt] = atMs
        elapsedNanos[writeAt] = nanos
        kind[writeAt] = k
        x[writeAt] = vx
        y[writeAt] = vy
        z[writeAt] = vz
        writeAt = (writeAt + 1) % capacity
        if (filled < capacity) filled++
    }

    /**
     * Every sample in [fromMs]..[toMs], oldest first.
     *
     * `sequence` is assigned HERE and not at insert, because it only has to
     * be unique within one millisecond of one kind — which is what the
     * table's composite key needs, and what stops two 200 Hz samples in the
     * same millisecond replacing each other.
     */
    @Synchronized
    fun window(fromMs: Long, toMs: Long): List<ImuSampleEntity> {
        val out = ArrayList<ImuSampleEntity>()
        val seen = HashMap<Long, Int>()
        val start = if (filled < capacity) 0 else writeAt
        for (i in 0 until filled) {
            val idx = (start + i) % capacity
            val k = kind[idx]
            if (k == KIND_NONE) continue
            val t = timestamp[idx]
            if (t < fromMs || t > toMs) continue
            // One counter per (ms, kind) pair.
            val key = t * 2 + k
            val seq = seen.getOrElse(key) { 0 }
            seen[key] = seq + 1
            out += ImuSampleEntity(
                timestamp = t, kind = kindName(k), sequence = seq,
                x = x[idx], y = y[idx], z = z[idx], elapsedNanos = elapsedNanos[idx],
            )
        }
        return out
    }

    /** The newest sample's wall-clock ms, or null when empty — the dedup mark. */
    @Synchronized
    fun newestMs(): Long? {
        if (filled == 0) return null
        return timestamp[(writeAt - 1 + capacity) % capacity]
    }

    @Synchronized
    fun clear() {
        writeAt = 0
        filled = 0
        java.util.Arrays.fill(kind, KIND_NONE)
    }

    companion object {
        const val KIND_NONE = -1
        const val KIND_ACCEL = 0
        const val KIND_GYRO = 1

        fun kindName(k: Int): String = if (k == KIND_GYRO) "gyro" else "accel"
    }
}
