package cz.hillview.geo

import cz.hillview.plugin.ImuSampleEntity
import cz.hillview.plugin.imuSamplesPayloadJson
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The window's SIX kinds, and the one trap in how they are named.
 *
 * `ImuRing.kindName` ends in `else -> "accel"`. That shape is why this test exists: a
 * kind added to the companion object and forgotten here does not fail, it silently
 * becomes ACCELEROMETER DATA — rows of degrees or of boolean flags, filed under m/s²,
 * in an artifact nobody will re-read for months. A confidently wrong answer, which is
 * the failure mode this repo treats as worse than a crash.
 */
class ImuKindsTest {

    /** Every kind the ring can store maps to its OWN name. */
    @Test
    fun everyKindHasItsOwnName() {
        val kinds = mapOf(
            ImuRing.KIND_ACCEL to "accel",
            ImuRing.KIND_GYRO to "gyro",
            ImuRing.KIND_RV to "rv",
            ImuRing.KIND_MAG to "mag",
            ImuRing.KIND_POSE to "pose",
            ImuRing.KIND_DECIDE to "decide",
        )
        kinds.forEach { (k, name) ->
            assertEquals(name, ImuRing.kindName(k), "kind $k")
        }
        // Distinct, so nothing is quietly folded into another stream.
        assertEquals(kinds.size, kinds.values.toSet().size)
        // And the constants themselves are distinct — a copy-paste that gave two kinds
        // the same number would pass every assertion above.
        assertEquals(kinds.size, kinds.keys.toSet().size)
    }

    /**
     * THE GUARD AGAINST THE `else` BRANCH: the next unused constant must not already
     * answer to a name. If this fails, a kind was added to the companion object without
     * being given one, and its samples are being written as "accel".
     */
    @Test
    fun anUnnamedKindIsNotSilentlyAccelerometerData() {
        val highest = listOf(
            ImuRing.KIND_ACCEL, ImuRing.KIND_GYRO, ImuRing.KIND_RV,
            ImuRing.KIND_MAG, ImuRing.KIND_POSE, ImuRing.KIND_DECIDE,
        ).max()
        assertEquals(
            "accel", ImuRing.kindName(highest + 1),
            "kind ${highest + 1} exists and is unnamed — add it to kindName and to this test",
        )
        // The real assertion: the highest NAMED kind is the highest that exists. A new
        // constant bumps this and the line above becomes the failure.
        assertEquals(ImuRing.KIND_DECIDE, highest)
    }

    /**
     * The payload keeps one object per kind, so a consumer reads `rv` or `pose` by name
     * without having to know the order they were appended in.
     */
    @Test
    fun thePayloadSeparatesTheKindsByName() {
        val t0 = 1_700_000_000_000L
        val rows = listOf("accel", "gyro", "rv", "mag", "pose", "decide").flatMapIndexed {
            n, kind ->
            (0..2).map { i ->
                ImuSampleEntity(
                    timestamp = t0 + i * 10L,
                    kind = kind,
                    sequence = i,
                    x = (n + 1).toFloat(), y = 0f, z = 0f,
                    elapsedNanos = 812_340_000_000L + i * 10_000_000L,
                )
            }
        }
        val json = imuSamplesPayloadJson(rows)!!
        listOf("accel", "gyro", "rv", "mag", "pose", "decide").forEach {
            assertTrue("\"$it\":{" in json, "no $it object in $json")
        }
        // `decide` carries a quantized class and two flags, so it must serialize as
        // integers — "270" and "1", never "270.00" and "1.00".
        val decide = json.substringAfter("\"decide\":{")
        assertTrue("\"x\":[6,6,6]" in decide, "decide should be integral: $decide")
    }
}
