package cz.hillview.capture

/**
 * A short history of sensor samples, so a capture can ask what the device was doing at
 * the instant it actually EXPOSED rather than at the instant the button was pressed.
 *
 * WHY A HISTORY AND NOT A CORRECTION. The exposure is 250 ms–1.2 s after the press and
 * the gap varies by tens of milliseconds between captures, so it cannot be calibrated
 * out. The alternative to keeping samples is integrating the gyro forward from the
 * press, which was measured to inject ~0.6° over a Quality-mode gap on a phone lying
 * still — bias, not motion. A remembered measurement beats a propagated one.
 *
 * WHY NEAREST AND NOT INTERPOLATION. The attitude stream runs at 33 Hz
 * (`SENSOR_DELAY_NORMAL_US`), so the nearest sample is within 15 ms. Rotating at 10°/s
 * that is 0.15°, an order of magnitude under the ~0.6° the gyro's own noise floor
 * contributes over a capture. Interpolating angles correctly (shortest arc, per axis)
 * would cost more than it could buy.
 *
 * Thread-safe because of who touches it: samples arrive on the collector that feeds the
 * capture's stamp fields, and the lookup happens on the camera callback.
 */
internal class SampleRing<T>(
    private val capacity: Int,
    private val instantOf: (T) -> Long,
) {
    private val items = ArrayDeque<T>(capacity)

    fun add(item: T) {
        // A sample with no monotonic instant cannot be looked up, so it is not kept —
        // better an empty ring, which falls back to the press-time value visibly, than
        // a ring of entries that silently never match.
        if (instantOf(item) <= 0L) return
        synchronized(items) {
            if (items.size >= capacity) items.removeFirst()
            items.addLast(item)
        }
    }

    /**
     * The sample closest to [atNs], or null when the ring holds nothing within
     * [toleranceNs] — which is the honest answer, and the caller then keeps whatever it
     * had rather than pretending.
     *
     * Deliberately accepts samples on BOTH sides of the instant. A sample 10 ms after
     * the exposure describes the device better than one 300 ms before it, and the
     * press-time rule's one-sided freshness test is what made that a problem.
     */
    fun nearest(atNs: Long, toleranceNs: Long): T? {
        if (atNs <= 0L) return null
        val snapshot = synchronized(items) { items.toList() }
        return snapshot.minByOrNull { kotlin.math.abs(instantOf(it) - atNs) }
            ?.takeIf { kotlin.math.abs(instantOf(it) - atNs) <= toleranceNs }
    }

    val size: Int get() = synchronized(items) { items.size }
}

/**
 * How far from the exposure a sample may be and still be said to describe it.
 *
 * Generous on purpose: at 33 Hz a hit is normally within 15 ms, so this only decides
 * what happens when the stream has stalled — and a 250 ms-old attitude is still a far
 * better description of the frame than one taken before a second of 3A work. Beyond
 * this the lookup declines and the press-time value stands, labelled as such.
 */
internal const val AT_EXPOSURE_TOLERANCE_NS = 250L * 1_000_000

/**
 * Samples to keep. At 33 Hz this is ~7.7 s — comfortably longer than the worst
 * press→exposure gap measured (1.2 s in Quality mode) plus the time the save takes to
 * ask, and small enough that the memory is not worth discussing.
 */
internal const val AT_EXPOSURE_RING_CAPACITY = 256
