package cz.hillview.plugin

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Whether the compass can be trusted at a given spot — the test that decides where an
 * azimuth sweep may be shot from, after the Prosek Rocks lookout was ruled out for a
 * disturbed field.
 */
class MagneticFieldTest {

    private fun rad(deg: Float) = (deg * PI / 180.0).toFloat()

    /**
     * THE INVARIANT, and the reason the dip is the useful number rather than the field's
     * components: it is the angle between two measured vectors, so NO rotation of the
     * phone can change it. That is what makes "turn on the spot and watch it hold still"
     * a valid field test — if it moves, the cause is the site or the magnetometer's own
     * calibration, never the rotation.
     */
    @Test
    fun theDipCannotChangeWhenThePhoneIsRotated() {
        // Prague-like: gravity down, the field 66 degrees below horizontal pointing north.
        val dip = rad(66f)
        val g = floatArrayOf(0f, 0f, 9.81f)                     // up, as the accelerometer reads at rest
        val b = floatArrayOf(0f, 49f * cos(dip), -49f * sin(dip))

        val reference = fieldDipDeg(g[0], g[1], g[2], b[0], b[1], b[2])!!
        assertEquals(66f, reference, 0.1f)

        var checked = 0
        for (yaw in 0 until 360 step 15) {
            for (pitch in -80..80 step 20) {
                for (roll in -170..180 step 20) {
                    // Rotate BOTH vectors by the same rotation — which is exactly what
                    // holding the phone differently does to the two readings.
                    val m = rotationMatrixOf(yaw.toFloat(), pitch.toFloat(), roll.toFloat())
                    val gr = apply(m, g)
                    val br = apply(m, b)
                    val d = fieldDipDeg(gr[0], gr[1], gr[2], br[0], br[1], br[2])!!
                    assertEquals(reference, d, 0.2f, "yaw $yaw pitch $pitch roll $roll")
                    // ...and the strength is rotation-invariant too.
                    assertEquals(49f, fieldMagnitudeUt(br[0], br[1], br[2]), 0.05f)
                    checked++
                }
            }
        }
        assertTrue(checked > 2_000, "swept only $checked orientations")
    }

    /** The sign convention: down is positive, which is the northern hemisphere's. */
    @Test
    fun theDipIsPositiveWhereTheFieldPointsDown() {
        // Field straight down, phone upright: full +90.
        assertEquals(90f, fieldDipDeg(0f, 0f, 9.81f, 0f, 0f, -49f)!!, 0.01f)
        // Field horizontal: the magnetic equator, 0.
        assertEquals(0f, fieldDipDeg(0f, 0f, 9.81f, 0f, 49f, 0f)!!, 0.01f)
        // Field straight up: the southern hemisphere's -90.
        assertEquals(-90f, fieldDipDeg(0f, 0f, 9.81f, 0f, 0f, 49f)!!, 0.01f)
    }

    /** No reading is not a reading of zero. */
    @Test
    fun anAbsentVectorHasNoDip() {
        assertNull(fieldDipDeg(0f, 0f, 0f, 0f, 49f, 0f))
        assertNull(fieldDipDeg(0f, 0f, 9.81f, 0f, 0f, 0f))
    }

    /**
     * The screening verdict. DELIBERATELY WEAK — it catches a site that cannot be used at
     * all, not the few degrees of error that would still spoil a careful azimuth, which
     * only the dip holding still through a rotation can rule out.
     */
    @Test
    fun theScreeningVerdictCatchesGrossDisturbanceOnly() {
        assertTrue(fieldLooksUndisturbed(49f, 66f))
        assertTrue(fieldLooksUndisturbed(44f, 61f), "5 off on both is still within slack")
        // A ferrous mass nearby: the strength climbs and the dip tilts.
        assertFalse(fieldLooksUndisturbed(92f, 66f))
        assertFalse(fieldLooksUndisturbed(49f, 30f))
        // Shielded or cancelled: too weak.
        assertFalse(fieldLooksUndisturbed(12f, 66f))
        // No dip at all cannot be judged clean.
        assertFalse(fieldLooksUndisturbed(49f, null))
        // And it is honest about being a SCREEN: a 6-degree heading-scale disturbance
        // passes, which is why the doc tells you to watch the dip instead.
        assertTrue(fieldLooksUndisturbed(49f, 60f))
    }

    // --- a rotation built independently of anything under test ---

    private fun rotationMatrixOf(yawDeg: Float, pitchDeg: Float, rollDeg: Float): FloatArray {
        val a = rad(yawDeg); val b = rad(pitchDeg); val c = rad(rollDeg)
        val rz = floatArrayOf(cos(a), -sin(a), 0f, sin(a), cos(a), 0f, 0f, 0f, 1f)
        val ry = floatArrayOf(cos(b), 0f, sin(b), 0f, 1f, 0f, -sin(b), 0f, cos(b))
        val rx = floatArrayOf(1f, 0f, 0f, 0f, cos(c), -sin(c), 0f, sin(c), cos(c))
        return mul(mul(rz, ry), rx)
    }

    private fun mul(a: FloatArray, b: FloatArray) = FloatArray(9) { i ->
        val r = i / 3; val c = i % 3
        a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c]
    }

    private fun apply(m: FloatArray, v: FloatArray) = floatArrayOf(
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2],
        m[3] * v[0] + m[4] * v[1] + m[5] * v[2],
        m[6] * v[0] + m[7] * v[1] + m[8] * v[2],
    )
}
