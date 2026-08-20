package cz.hillview.capture

import android.util.Log
import kotlin.math.abs
import kotlin.math.pow

private const val TAG = "hv-SceneMeter"

/**
 * Continuous metering that never touches auto-exposure.
 *
 * Auto-exposure is a feedback loop in the ISP: it reduces each frame to
 * luminance statistics, compares them against a target, and corrects the
 * exposure product for the next frame, damped so it settles over several
 * frames. That is why handing the camera back to AE costs a WINDOW rather
 * than an instant — and why the cost cannot be chunked, since turning AE
 * off throws away its convergence and the next window restarts from
 * whatever we pinned.
 *
 * But metering itself only needs ONE frame. We set the exposure, so we know
 * the time and the gain; image brightness is proportional to scene
 * luminance × exposure × gain, so a single frame at a known exposure solves
 * for the scene:
 *
 *     product_needed = product_used × (target_luma / measured_luma)
 *
 * That is a measurement, not a search — no AE handover, no convergence
 * wait, no preview pump, and nothing between a shutter press and the
 * shutter. It also deletes the per-shot metering window from interval
 * capture, which is the throughput this app exists to protect.
 *
 * The catch, handled by damping: preview luma has the ISP's tone curve
 * applied, so it is NOT linear in scene luminance. One big correction would
 * overshoot. Successive cheap samples walking toward the answer converge
 * anyway, and this runs continuously, so "walking" costs nothing.
 */
class SceneMeter {

    companion object {
        /**
         * Mid-grey in a tone-mapped preview. Not 128: ISP curves lift the
         * midtones, so an average scene lands above linear mid-grey, and
         * metering to 128 underexposes. Tunable — this is the one number
         * that decides whether the app's idea of "correct" matches yours.
         */
        const val TARGET_LUMA = 110.0

        /**
         * Fraction of the correction applied per sample, in log space. Full
         * correction would ring against the tone curve; a half step settles
         * in two or three samples and rides out a single odd frame.
         */
        const val DAMPING = 0.5

        /** Ignore frames this far into clipping: they carry no information. */
        const val LUMA_FLOOR = 2.0
        const val LUMA_CEILING = 253.0
    }

    /**
     * The estimate, as an exposure product in (ns × ISO). Null until the
     * first usable frame — callers keep their previous behaviour until then.
     */
    @Volatile
    private var product: Double? = null

    /** Whether the estimate has moved recently, for logging/diagnostics. */
    @Volatile
    var lastMeasuredLuma: Double = 0.0
        private set

    /**
     * One frame's worth of evidence: the mean luma it came out at, and the
     * exposure that produced it.
     */
    fun onFrame(meanLuma: Double, exposureNs: Long, iso: Int) {
        if (exposureNs <= 0 || iso <= 0) return
        lastMeasuredLuma = meanLuma
        val used = exposureNs.toDouble() * iso.toDouble()
        if (meanLuma <= LUMA_FLOOR || meanLuma >= LUMA_CEILING) {
            // Clipped: the correction direction is known but its magnitude
            // is not, so step by a fixed stop rather than by a ratio that
            // would be arbitrarily large.
            val stop = if (meanLuma <= LUMA_FLOOR) 2.0 else 0.5
            product = (product ?: used) * stop
            return
        }
        val wanted = used * (TARGET_LUMA / meanLuma)
        val current = product
        product = if (current == null) {
            wanted
        } else {
            // Geometric (log-space) step: exposure is multiplicative, so a
            // half step means half a stop of the error, not half its ns.
            current * (wanted / current).pow(DAMPING)
        }
    }

    /** Seed from what AE chose, so switching to a rule starts converged. */
    fun seedFromAutoExposure(exposureNs: Long, iso: Int) {
        if (exposureNs <= 0 || iso <= 0) return
        product = exposureNs.toDouble() * iso.toDouble()
    }

    fun reset() {
        product = null
    }

    /**
     * The estimate as the (exposure, iso) pair [planExposure] consumes. The
     * split is arbitrary — only the product carries meaning — so it is
     * reported against a reference ISO to keep the numbers readable in
     * logs and in the sidecar/provenance.
     */
    fun meteredPair(referenceIso: Int = 100): Pair<Long, Int>? {
        val p = product ?: return null
        val exposure = (p / referenceIso).toLong().coerceAtLeast(1L)
        return exposure to referenceIso
    }

    fun debugLine(): String {
        val p = product
        return if (p == null) "scene: unmetered" else
            "scene: luma=%.0f product=%.3g".format(lastMeasuredLuma, p)
    }
}

/**
 * Mean luma from a YUV_420_888 Y plane, subsampled hard.
 *
 * A few thousand samples describe the frame's exposure as well as a million
 * do — this runs per analysis frame, so its cost has to round to nothing.
 */
fun meanLumaSubsampled(
    plane: java.nio.ByteBuffer,
    width: Int,
    height: Int,
    rowStride: Int,
    targetSamples: Int = 3_000,
): Double {
    if (width <= 0 || height <= 0) return 0.0
    val step = maxOf(1, kotlin.math.sqrt((width.toDouble() * height / targetSamples)).toInt())
    var sum = 0L
    var count = 0
    var y = 0
    while (y < height) {
        val rowStart = y * rowStride
        var x = 0
        while (x < width) {
            val index = rowStart + x
            if (index < plane.limit()) {
                sum += (plane.get(index).toInt() and 0xFF)
                count++
            }
            x += step
        }
        y += step
    }
    return if (count == 0) 0.0 else sum.toDouble() / count
}
