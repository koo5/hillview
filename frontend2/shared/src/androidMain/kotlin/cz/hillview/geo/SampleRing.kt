package cz.hillview.geo

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
 * IT LIVES IN THE ENGINE, and the first version did not — that cost a measurable amount
 * of quality. Fed from the capture's stamp setters, the samples reached it through two
 * conflating StateFlows and a collector on the composition's dispatcher, so whenever
 * Compose was busy the intermediate values were DROPPED rather than queued. Twenty
 * uploaded photos showed the result: attitude hits +-88 ms from the exposure, a 33 Hz
 * stream arriving as roughly 9 Hz. Fed at the source, on the sensor thread, there is
 * nothing to conflate. The one-state allowlist already made this argument for the IMU
 * ring — "a 100 Hz buffer is not user-facing state and has no business passing through
 * recomposition".
 *
 * Thread-safe because of who touches it: samples arrive on the sensor thread and the
 * lookup happens on the camera callback.
 */
/**
 * BOUNDED BY TIME, NOT BY COUNT — changed 2026-09-28, after the count-bounded version
 * was measured at 1/29th of its documented span.
 *
 * It held 256 samples and the comment said "~7.7 s at 33 Hz". On a walking interval run
 * the real span was **268 ms, stdev 17** (n = 20 uploaded photos, derived as
 * `exposure_to_jpeg_ms + inertial.age_ms`): 256 samples over 268 ms is 956 samples/s
 * into the motion ring, i.e. ~478 Hz from each of gravity and linear acceleration where
 * `SENSOR_DELAY_NORMAL_US` had asked for 33. `registerListener`'s rate is a HINT, and
 * this process has another client — the IMU window — registering accelerometer at
 * `SENSOR_DELAY_FASTEST`, which raises the delivery rate of the whole derived family.
 *
 * The consequence was not subtle: the lookup happens at the SAVE, and on 12 of 70
 * photos the save was slower than the ring was long, so the exposure's samples had
 * already been evicted and the capture fell back to the press. `exposure_to_jpeg_ms`
 * separated the two cases cleanly — 275 ms mean on the photos that hit, 914 ms on the
 * ones that missed.
 *
 * A count is a PROXY for a duration, and the proxy silently changed meaning by 29x when
 * another part of the app touched an unrelated sensor. The duration is the actual
 * requirement, so it is what the ring is now given; [maxSamples] remains only as a
 * memory backstop, and [capped] says when it is the binding constraint so that failure
 * cannot be silent the way the last one was.
 */
internal class SampleRing<T>(
    private val windowNs: Long,
    private val maxSamples: Int,
    private val instantOf: (T) -> Long,
) {
    private val items = ArrayDeque<T>()

    /** True once [maxSamples] has ever evicted a sample the window would have kept. */
    @Volatile
    var capped: Boolean = false
        private set

    fun add(item: T) {
        // A sample with no monotonic instant cannot be looked up, so it is not kept —
        // better an empty ring, which falls back to the press-time value visibly, than
        // a ring of entries that silently never match.
        val at = instantOf(item)
        if (at <= 0L) return
        synchronized(items) {
            items.addLast(item)
            // Age relative to the NEWEST SAMPLE, not to a clock read here. The ring is
            // fed on the sensor thread and read on the camera thread, and the samples
            // carry the instant that matters; calling elapsedRealtimeNanos() would make
            // this class platform-bound and untestable for the sake of a value it
            // already has. Out-of-order arrivals (gravity and linear acceleration are
            // two callbacks) only ever delay an eviction by one sample.
            while (items.size > 1 && at - instantOf(items.first()) > windowNs) {
                items.removeFirst()
            }
            while (items.size > maxSamples) {
                items.removeFirst()
                capped = true
            }
        }
    }

    /**
     * How much time the ring currently holds. The number the old `capacity` was a proxy
     * for, exposed so a declining lookup can be diagnosed instead of guessed at.
     */
    val spanNs: Long
        get() = synchronized(items) {
            if (items.size < 2) 0L else instantOf(items.last()) - instantOf(items.first())
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
 * How much HISTORY to keep, which is the thing the ring is actually for.
 *
 * What has to fit is exposure → lookup, not press → exposure: the exposure's samples
 * must still be there when the save asks for them. Measured worst case on a walking
 * interval run is `exposure_to_jpeg_ms` = 2010 ms, and Quality mode's 1758 ms
 * press→exposure sits on top of a similar save; 8 s is about 4x the worst observed,
 * which is the margin a value that failed silently once has earned.
 *
 * Note what this does NOT depend on: the sample rate. That was the bug.
 *
 * WHAT IT COSTS, stated rather than left to be discovered the way the last number was.
 * The motion ring is the expensive one: ~1 kHz x 8 s = ~8 000 `DeviceMotionSample`,
 * each holding two three-element `List<Float>` of BOXED floats, so roughly 2.3 MB
 * retained; the attitude ring adds a few hundred kB. That is retention, not extra
 * allocation — the samples are built per event either way — and the peak only occurs
 * while the IMU window is running, which is the same condition under which the history
 * is wanted. The `imuRing` beside it already holds 16 000 samples. If this ever needs
 * to come down, unboxing those two lists buys most of it back without shortening the
 * window, which is the axis that must not be traded.
 */
internal const val AT_EXPOSURE_RING_WINDOW_NS = 8L * 1_000_000_000

/**
 * The memory backstop, not the design. At the ~1 kHz the motion ring was measured
 * receiving, the window above is ~8 000 samples, so this only binds if the delivery
 * rate rises by half again — and `SampleRing.capped` says so out loud when it does,
 * because the previous silent version of this failure cost twelve photos before anyone
 * noticed. For comparison the IMU ring already holds 16 000.
 */
internal const val AT_EXPOSURE_RING_MAX_SAMPLES = 12_000
