package cz.hillview.geo

import cz.hillview.plugin.ImuSampleEntity
import cz.hillview.plugin.imuSamplesPayloadJson
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The columnar, delta-encoded payload a photo's raw IMU window travels as
 * (docs/recon-capture-metadata.md, Phase 5).
 *
 * Tested here rather than against a live engine because it is a PURE function
 * over rows — which is also why it lives in shared-kt beside
 * `summariseImuWindow`: the capture path and the upload pipeline both produce
 * one, and one implementation means the two cannot disagree.
 */
class ImuPayloadTest {

    private val t0 = 1_700_000_000_000L

    private fun accel(i: Int, x: Float = 0f, y: Float = 0f, z: Float = 0f, stepUs: Long = 2_500) =
        ImuSampleEntity(
            timestamp = t0 + (i * stepUs) / 1_000,
            kind = "accel",
            sequence = i,
            x = x, y = y, z = z,
            elapsedNanos = 812_340_000_000L + i * stepUs * 1_000,
        )

    private fun gyro(i: Int, x: Float = 0f, stepUs: Long = 2_500) =
        ImuSampleEntity(
            timestamp = t0 + (i * stepUs) / 1_000,
            kind = "gyro",
            sequence = i,
            x = x, y = 0f, z = 0f,
            elapsedNanos = 812_340_000_000L + i * stepUs * 1_000,
        )

    /**
     * A REAL window must not drift. Every other test here steps by whole
     * microseconds, which is exactly why none of them caught this: 2 500 ns
     * divides evenly, so truncation loses nothing and the bug is invisible.
     *
     * The device does not oblige. The Armor 22 delivers ~398 Hz — 2 512.5 us —
     * and the encoder used to truncate each gap on its own, losing ~500 ns per
     * gap. Over a 6-second window that is ~1.2 ms of accumulated shortfall, which
     * is how a four-capture audit reassembling by decoded wall time came out two
     * samples short of what the summaries claimed.
     */
    @Test
    fun theTimelineDoesNotDriftAcrossARealLengthWindow() {
        val stepNs = 2_512_500L          // 398 Hz: NOT a whole number of us
        val n = 2_388                    // ~6 s, the size of a real window
        val baseNs = 812_340_000_000L
        val rows = (0 until n).map { i ->
            ImuSampleEntity(
                timestamp = t0 + (i * stepNs) / 1_000_000,
                kind = "accel",
                sequence = i,
                x = 0f, y = 0f, z = 0f,
                elapsedNanos = baseNs + i * stepNs,
            )
        }
        val json = imuSamplesPayloadJson(rows)!!
        val gaps = Regex(""""dt_us":\[([^]]*)]""").find(json)!!
            .groupValues[1].split(",").map { it.toLong() }
        assertEquals(n - 1, gaps.size)

        val trueSpanUs = (rows.last().elapsedNanos - rows.first().elapsedNanos) / 1_000
        val decodedSpanUs = gaps.sum()
        assertTrue(
            kotlin.math.abs(decodedSpanUs - trueSpanUs) <= 1,
            "timeline drifted ${trueSpanUs - decodedSpanUs}us over $n samples " +
                "(decoded $decodedSpanUs vs true $trueSpanUs)",
        )
        // The mechanism, not just the outcome: the remainder is carried, so gaps
        // alternate instead of every one of them rounding the same way down.
        assertTrue(2_512L in gaps && 2_513L in gaps, "gaps never alternate: ${gaps.take(6)}")
    }

    @Test
    fun anEmptyWindowHasNoPayload() {
        assertNull(imuSamplesPayloadJson(emptyList()))
    }

    /** The documented shape, exactly, so a decoder can be written against it. */
    @Test
    fun theShapeIsColumnarPerSensor() {
        val json = imuSamplesPayloadJson(
            listOf(
                accel(0, x = 0.012f, y = -1.5f, z = 9.81f),
                accel(1, x = 0.013f, y = -1.5f, z = 9.807f),
            ),
        )!!
        assertEquals(
            """{"accel":{"t0_ms":$t0,"t0_ns":812340000000,"dt_us":[2500],""" +
                """"x":[0.012,0.013],"y":[-1.5,-1.5],"z":[9.81,9.807]}}""",
            json,
        )
    }

    /**
     * n samples yield n-1 gaps. The off-by-one here is the difference between a
     * decoder that lines up and one that walks off the end of an axis.
     */
    @Test
    fun thereAreOneFewerGapsThanSamples() {
        val json = imuSamplesPayloadJson((0..4).map { accel(it) })!!
        assertTrue("\"dt_us\":[2500,2500,2500,2500]" in json, json)
        assertEquals(5, Regex("""\"x\":\[([^]]*)]""").find(json)!!.groupValues[1].split(",").size)
    }

    /**
     * Gaps come from the MONOTONIC clock, not the wall clock. A window read
     * across an NTP step must not reorder or show a negative interval — the
     * reason `elapsedNanos` travels beside `timestamp` in the first place.
     */
    @Test
    fun theGapsSurviveAWallClockStep() {
        val a = accel(0)
        // The wall clock jumps BACK half a second between two samples 2.5 ms apart.
        val b = accel(1).copy(timestamp = a.timestamp - 500)
        val json = imuSamplesPayloadJson(listOf(a, b))!!
        assertTrue("\"dt_us\":[2500]" in json, json)
    }

    /** Both sensors travel, each with its own base and its own gaps. */
    @Test
    fun eachSensorGetsItsOwnObject() {
        val json = imuSamplesPayloadJson(
            listOf(accel(0, z = 9.81f), gyro(0, x = 0.0123f), accel(1, z = 9.8f)),
        )!!
        assertTrue("\"accel\":{" in json, json)
        assertTrue("\"gyro\":{" in json, json)
        // accel keeps both of its samples, gyro its one.
        assertTrue("\"z\":[9.81,9.8]" in json, json)
        assertTrue("\"dt_us\":[]" in json, json)
    }

    /**
     * Rounded to each sensor's own resolution — gyro finer than accel, because
     * a gyroscope resolves ~1e-4 rad/s and an accelerometer ~1e-3 m/s2.
     */
    @Test
    fun eachSensorIsRoundedToWhatItCanActuallyResolve() {
        val a = imuSamplesPayloadJson(listOf(accel(0, x = 0.0123456f)))!!
        assertTrue("\"x\":[0.012]" in a, a)
        val g = imuSamplesPayloadJson(listOf(gyro(0, x = 0.0123456f)))!!
        assertTrue("\"x\":[0.0123]" in g, g)
    }

    /**
     * Rounding must not produce `0,012`. `String.format` follows the default
     * locale, and in a Czech locale — this project's author's phone — the
     * decimal separator is a comma, which would make the payload invalid JSON
     * for every reader.
     */
    @Test
    fun aCommaDecimalLocaleCannotCorruptThePayload() {
        val original = java.util.Locale.getDefault()
        try {
            java.util.Locale.setDefault(java.util.Locale.forLanguageTag("cs-CZ"))
            val json = imuSamplesPayloadJson(listOf(accel(0, x = 0.012f)))!!
            assertTrue("\"x\":[0.012]" in json, json)
            assertTrue("0,012" !in json, json)
        } finally {
            java.util.Locale.setDefault(original)
        }
    }

    /** A whole number prints as `0`, not `0.000` — and never as `-0`. */
    @Test
    fun zeroAndWholeNumbersPrintShort() {
        val json = imuSamplesPayloadJson(listOf(accel(0, x = 0f, y = -0.0001f, z = 2f)))!!
        assertTrue("\"x\":[0]" in json, json)
        assertTrue("\"y\":[0]" in json, json)   // rounds to -0.000 -> 0, not "-0"
        assertTrue("\"z\":[2]" in json, json)
        assertTrue("-0" !in json, json)
    }

    /**
     * The point of the encoding. A realistic window must stay a few tens of KB,
     * because it rides in the upload metadata beside a multi-megabyte JPEG and
     * the whole design rests on it being a rounding error next to the image.
     */
    @Test
    fun aRealisticWindowStaysSmall() {
        // 6 s at 400 Hz on two sensors — the ±3 s window at a fast phone's rate.
        val rows = (0 until 2_400).flatMap { listOf(accel(it, x = 0.012f, z = 9.81f), gyro(it, x = 0.01f)) }
        val json = imuSamplesPayloadJson(rows)!!
        assertTrue(json.length < 120_000, "payload was ${json.length} bytes")
        // ...and it really did carry every sample, not a truncated prefix.
        fun countIn(kind: String): Int {
            val obj = json.substringAfter("\"$kind\":{")
            return obj.substringAfter("\"x\":[").substringBefore("]").split(",").size
        }
        assertEquals(2_400, countIn("accel"))
        assertEquals(2_400, countIn("gyro"))
        println("6 s @ 400 Hz x2 sensors: ${json.length} bytes of JSON")
    }
}
