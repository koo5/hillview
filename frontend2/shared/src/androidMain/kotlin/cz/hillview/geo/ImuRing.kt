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

        /**
         * `TYPE_ROTATION_VECTOR` — the HAL's own fused attitude, at window rate.
         *
         * Three components, not four: Android's `getRotationMatrixFromVector`
         * recovers `w` as `sqrt(1 - x² - y² - z²)` when handed a 3-element vector,
         * so the quaternion is fully determined by its vector part and this fits
         * the existing (x, y, z) row with no migration. What IS lost is the
         * optional 5th element, the estimated heading accuracy — recorded per
         * photo in `attitude.fused_sensor_accuracy` instead, which is the shutter's
         * value rather than the series.
         *
         * Added 2026-10-10 because the series is what two separate attitude faults
         * needed and neither had: with only accel and gyro in the window, the
         * TRUE motion could be reconstructed offline but what the fusion REPORTED
         * during it could not, so every question about it needed a person watching
         * a screen.
         */
        const val KIND_RV = 2

        /**
         * `TYPE_MAGNETIC_FIELD`, µT in the device frame.
         *
         * The one sensor from which an attitude can be computed WITHOUT the HAL's
         * fusion: `getRotationMatrix(accel, mag)` gives an independent answer, so a
         * disagreement with [KIND_RV] is the fusion's and can be characterised rather
         * than merely patched. That matters for the azimuth mirror this device shows in
         * landscape above the horizon, which is currently corrected behind a pref with
         * no account of WHY it happens.
         */
        const val KIND_MAG = 3

        /**
         * WHAT THE APP PUBLISHED — (pointing bearing, pitch, image roll) in degrees,
         * after both corrections, at the rate the sensor stack produces them.
         *
         * In principle derivable from [KIND_RV] plus [KIND_ACCEL] plus the user's pref,
         * because the branch test now asks gravity. In practice that derivation means
         * checking out the exact commit and re-running its arithmetic, and the question
         * worth answering fast is "did the number the user saw jump, and when" — so the
         * OUTPUT is recorded beside the inputs. Comparing the two is how a fault in our
         * own code is told from a fault in the HAL's, which has taken three attempts to
         * settle by reasoning alone.
         */
        const val KIND_POSE = 4

        /**
         * THE DECISIONS, packed into one row: (orientation class in degrees, the 180°
         * branch correction fired, the azimuth mirror fired).
         *
         * The class is the only input here that no sensor series can reconstruct — see
         * `OrientationSensorData.deviceRotationDeg`. The two flags are derivable, and are
         * recorded anyway because the row has the space and because a flag beats
         * re-deriving a decision from thresholds that may have moved since.
         */
        const val KIND_DECIDE = 5

        fun kindName(k: Int): String = when (k) {
            KIND_GYRO -> "gyro"
            KIND_RV -> "rv"
            KIND_MAG -> "mag"
            KIND_POSE -> "pose"
            KIND_DECIDE -> "decide"
            else -> "accel"
        }
    }
}
