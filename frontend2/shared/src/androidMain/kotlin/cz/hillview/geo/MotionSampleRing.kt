package cz.hillview.geo

import cz.hillview.map.DeviceMotionSample
import kotlin.math.abs

/**
 * Full-rate motion history in fixed primitive arrays. Recording a callback allocates
 * no sample, vector list, or boxed float; only a successful lookup builds a snapshot.
 *
 * The time window and capacity backstop match [SampleRing]. Slots follow callback
 * order, since gravity and linear acceleration may arrive slightly out of order.
 * At 12,000 slots the arrays occupy about 0.5 MB, independent of the sensor rate.
 */
internal class MotionSampleRing(
    private val windowNs: Long,
    private val maxSamples: Int,
) {
    init {
        require(windowNs >= 0L)
        require(maxSamples > 0)
    }

    private val wallMs = LongArray(maxSamples)
    private val elapsedNs = LongArray(maxSamples)
    private val presence = ByteArray(maxSamples)
    private val gravityX = FloatArray(maxSamples)
    private val gravityY = FloatArray(maxSamples)
    private val gravityZ = FloatArray(maxSamples)
    private val linearX = FloatArray(maxSamples)
    private val linearY = FloatArray(maxSamples)
    private val linearZ = FloatArray(maxSamples)
    private var first = 0
    private var filled = 0

    @Volatile
    var capped: Boolean = false
        private set

    @Synchronized
    fun add(
        atMs: Long,
        nanos: Long,
        hasGravity: Boolean,
        gx: Float,
        gy: Float,
        gz: Float,
        hasLinear: Boolean,
        lx: Float,
        ly: Float,
        lz: Float,
    ) {
        if (nanos <= 0L) return
        // Evict by age before enforcing capacity, so capped only reports a sample
        // lost while still inside the requested history window.
        while (filled > 0 && nanos - elapsedNs[first] > windowNs) {
            first = (first + 1) % maxSamples
            filled--
        }
        if (filled == maxSamples) {
            first = (first + 1) % maxSamples
            filled--
            capped = true
        }
        val index = (first + filled) % maxSamples
        wallMs[index] = atMs
        elapsedNs[index] = nanos
        presence[index] = ((if (hasGravity) 1 else 0) or (if (hasLinear) 2 else 0)).toByte()
        gravityX[index] = gx
        gravityY[index] = gy
        gravityZ[index] = gz
        linearX[index] = lx
        linearY[index] = ly
        linearZ[index] = lz
        filled++
    }

    /** Nearest on either side of the exposure; ties keep the earlier callback. */
    @Synchronized
    fun nearest(atNs: Long, toleranceNs: Long): DeviceMotionSample? {
        if (atNs <= 0L) return null
        var nearestIndex = -1
        var nearestDistance = Long.MAX_VALUE
        for (offset in 0 until filled) {
            val index = (first + offset) % maxSamples
            val distance = abs(elapsedNs[index] - atNs)
            if (distance < nearestDistance) {
                nearestIndex = index
                nearestDistance = distance
            }
        }
        if (nearestIndex < 0 || nearestDistance > toleranceNs) return null
        val index = nearestIndex
        val mask = presence[index].toInt()
        return DeviceMotionSample(
            gravity = if ((mask and 1) != 0) {
                listOf(gravityX[index], gravityY[index], gravityZ[index])
            } else null,
            linearAcceleration = if ((mask and 2) != 0) {
                listOf(linearX[index], linearY[index], linearZ[index])
            } else null,
            atMs = wallMs[index],
            elapsedNs = elapsedNs[index],
        )
    }

    val size: Int
        @Synchronized get() = filled

    val spanNs: Long
        @Synchronized get() = if (filled < 2) 0L else {
            elapsedNs[(first + filled - 1) % maxSamples] - elapsedNs[first]
        }
}
