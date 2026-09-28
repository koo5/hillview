package cz.hillview.geo

import cz.hillview.map.DeviceMotionSample

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
    @Volatile
    private var gravity: List<Float>? = null

    @Volatile
    private var linear: List<Float>? = null

    fun gravity(x: Float, y: Float, z: Float) {
        gravity = listOf(x, y, z)
    }

    fun linear(x: Float, y: Float, z: Float) {
        linear = listOf(x, y, z)
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
    fun sampleAt(atMs: Long, elapsedNs: Long) = DeviceMotionSample(
        gravity = gravity,
        linearAcceleration = linear,
        atMs = atMs,
        elapsedNs = elapsedNs,
    )

    /** Nothing is being sensed any more, so stop reporting what was. */
    fun reset() {
        gravity = null
        linear = null
    }
}
