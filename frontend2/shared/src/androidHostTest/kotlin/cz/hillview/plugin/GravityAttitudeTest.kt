package cz.hillview.plugin

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * PITCH AND ROLL FROM GRAVITY, which is what the app publishes from 2026-10-10.
 *
 * The claim being pinned is not that these formulas are arbitrary conventions we have
 * chosen, but that they agree with the camera-axis geometry the fused matrix produced —
 * because a change of SOURCE that also changed the meaning would silently reinterpret
 * every stored field. So each case builds an attitude, derives gravity FROM it, and
 * checks that gravity's answer matches the pose's.
 */
class GravityAttitudeTest {

    private fun rad(deg: Float) = (deg * PI / 180.0).toFloat()

    /**
     * Gravity as the device would measure it for a given attitude: world down, expressed
     * in device coordinates, negated because an accelerometer at rest reads +g along UP.
     * World up in device coordinates is the matrix's third ROW.
     */
    private fun gravityFor(m: FloatArray) = floatArrayOf(9.81f * m[6], 9.81f * m[7], 9.81f * m[8])

    @Test
    fun gravityAgreesWithTheMatrixPoseAcrossTheSphere() {
        var checked = 0
        var worstPitch = 0f
        var worstRoll = 0f
        for (lat in -80..80 step 20) {
            for (lon in 0 until 360 step 40) {
                for (angle in 20..340 step 40) {
                    val la = rad(lat.toFloat())
                    val lo = rad(lon.toFloat())
                    val h = rad(angle.toFloat()) / 2f
                    var w = cos(h)
                    var x = cos(la) * sin(lo) * sin(h)
                    var y = cos(la) * cos(lo) * sin(h)
                    var z = sin(la) * sin(h)
                    if (w < 0f) { w = -w; x = -x; y = -y; z = -z }
                    val m = rotationMatrixFromVector(x, y, z)
                    val pose = cameraPoseFromRotationMatrix(m) ?: continue
                    val g = gravityFor(m)

                    // Pitch always, and it must match the pose's to float precision.
                    val gp = gravityPitchDeg(g[0], g[1], g[2])!!
                    worstPitch = kotlin.math.max(worstPitch, kotlin.math.abs(gp - pose.pitchDeg))

                    // Roll only where gravity has an in-plane direction to give one.
                    if (gravityRollConditioning(g[0], g[1], g[2]) >= GRAVITY_ROLL_FLOOR) {
                        val gr = gravityRollDeg(g[0], g[1])
                        worstRoll = kotlin.math.max(
                            worstRoll,
                            kotlin.math.abs(signedDegreeDelta(gr, pose.imageRollDeg)),
                        )
                    }
                    checked++
                }
            }
        }
        assertTrue(checked > 500, "swept only $checked attitudes")
        assertTrue(worstPitch < 0.1f, "pitch disagreed by up to $worstPitch deg")
        assertTrue(worstRoll < 0.1f, "roll disagreed by up to $worstRoll deg")
    }

    /** Positive looking DOWN, which is the convention the field has always carried. */
    @Test
    fun thePitchIsPositiveLookingDown() {
        // Flat on its back, screen up: the lens points at the table, straight down.
        assertEquals(90f, gravityPitchDeg(0f, 0f, 9.81f)!!, 0.01f)
        // Upright portrait: level.
        assertEquals(0f, gravityPitchDeg(0f, 9.81f, 0f)!!, 0.01f)
        // Face down: the lens points at the sky.
        assertEquals(-90f, gravityPitchDeg(0f, 0f, -9.81f)!!, 0.01f)
    }

    /**
     * WHERE GRAVITY MUST DEFER. Flat, the optical axis is vertical and the image's
     * rotation about it is an AZIMUTH — which gravity cannot see at all. The conditioning
     * says so, and the service publishes the matrix's roll there instead.
     */
    @Test
    fun theRollHasNoGravityAnswerWithThePhoneFlat() {
        // Flat: all of gravity is along z, nothing in the screen's plane.
        assertEquals(0f, gravityRollConditioning(0f, 0f, 9.81f), 0.001f)
        assertTrue(gravityRollConditioning(0f, 0f, 9.81f) < GRAVITY_ROLL_FLOOR)
        // The floor is sin(15.07°) = 0.26, so 15° is BELOW it and 16° above. Both sides
        // are pinned, which also records what the constant means in degrees — the doc
        // says "~15° off flat" and that rounds the wrong way at the boundary.
        fun conditioningAt(deg: Float): Float {
            val t = rad(deg)
            return gravityRollConditioning(0f, 9.81f * sin(t), 9.81f * cos(t))
        }
        assertTrue(conditioningAt(15f) < GRAVITY_ROLL_FLOOR, "15 deg: ${conditioningAt(15f)}")
        assertTrue(conditioningAt(16f) >= GRAVITY_ROLL_FLOOR, "16 deg: ${conditioningAt(16f)}")
        // Pitch, by contrast, never needs an in-plane component.
        assertEquals(90f, gravityPitchDeg(0f, 0f, 9.81f)!!, 0.01f)
    }

    /** No reading is not a reading of zero. */
    @Test
    fun anAbsentVectorHasNoPitch() {
        assertNull(gravityPitchDeg(0f, 0f, 0f))
    }
}
