package cz.hillview.geo

import cz.hillview.map.DeviceMotionSample

private const val MOTION_PUBLICATION_INTERVAL_NS = 50_000_000L

/**
 * Latches gravity and linear acceleration — which arrive on SEPARATE sensor callbacks —
 * and assembles the pair into one sample.
 *
 * IT EXISTS AS A CLASS BECAUSE THE ASSEMBLY WAS SILENTLY WRONG FOR A DAY. The listener
 * held both vectors correctly and then built the sample without them:
 *
 *     _motion.value = DeviceMotionSample(
 *         atMs = imuWallClockFor(event.timestamp),
 *         elapsedNs = event.timestamp,
 *     )                      // gravity = , linearAcceleration = — dropped in a rewrite
 *
 * `DeviceMotionSample.gravity` and `.linearAcceleration` are nullable with defaults, so
 * dropping them COMPILED, and ~2 800 uploaded photos carried `inertial.age_ms` with no
 * vectors to date — a freshness figure describing a reading that was not there. The
 * ring tests could not see it: they construct samples carrying gravity themselves, so
 * they round-tripped a vector the real listener never supplied. Exactly the shape of
 * the `stored_count` bug (docs/recon-capture-metadata.md): the serializer was never
 * wrong, the call site dropped the value.
 *
 * So the assembly is a unit with a test, and the sensor-type dispatch stays in
 * [GeoEngine] where the platform constants belong.
 */
internal class MotionSampleAssembler {
    // Mutable primitives stay behind this object's monitor. Sensor callbacks only
    // copy them into the primitive ring; lists are built when a snapshot is needed.
    private var hasGravity = false
    private var gravityX = 0f
    private var gravityY = 0f
    private var gravityZ = 0f
    private var hasLinear = false
    private var linearX = 0f
    private var linearY = 0f
    private var linearZ = 0f
    private var published = false
    private var lastPublicationNs = 0L

    @Synchronized
    fun gravity(x: Float, y: Float, z: Float) {
        gravityX = x
        gravityY = y
        gravityZ = z
        hasGravity = true
    }

    @Synchronized
    fun linear(x: Float, y: Float, z: Float) {
        linearX = x
        linearY = y
        linearZ = z
        hasLinear = true
    }

    /** Copy the latched pair at raw sensor rate without creating a snapshot. */
    @Synchronized
    fun recordAt(ring: MotionSampleRing, atMs: Long, elapsedNs: Long) {
        ring.add(
            atMs, elapsedNs,
            hasGravity, gravityX, gravityY, gravityZ,
            hasLinear, linearX, linearY, linearZ,
        )
    }

    /**
     * The pair as of now, stamped with the instant of the sample that TRIGGERED the
     * publication — both clocks describing the event rather than the callback, because
     * these sensors batch and delivery is a third of a second behind.
     *
     * The other half of the pair may still be null: gravity and linear acceleration
     * arrive independently, so the first sample after a re-registration carries one
     * vector. That is honest and the serializer handles it; what must never happen is
     * BOTH being null while a timestamp claims a reading exists.
     */
    @Synchronized
    fun sampleAt(atMs: Long, elapsedNs: Long) = DeviceMotionSample(
        gravity = if (hasGravity) listOf(gravityX, gravityY, gravityZ) else null,
        linearAcceleration = if (hasLinear) listOf(linearX, linearY, linearZ) else null,
        atMs = atMs,
        elapsedNs = elapsedNs,
    )

    /**
     * Latest-value stream for the press-time stamp, sampled at 50 ms sensor-time
     * intervals. Gate on event time so batched delivery cannot leave this stream
     * stuck on the first event of a batch. Both snapshot clocks describe the event.
     */
    @Synchronized
    fun sampleForPublication(atMs: Long, elapsedNs: Long): DeviceMotionSample? {
        if (published && elapsedNs - lastPublicationNs < MOTION_PUBLICATION_INTERVAL_NS) return null
        published = true
        lastPublicationNs = elapsedNs
        return sampleAt(atMs, elapsedNs)
    }

    /** Nothing is being sensed any more, so stop reporting what was. */
    @Synchronized
    fun reset() {
        hasGravity = false
        hasLinear = false
        published = false
        lastPublicationNs = 0L
    }
}
