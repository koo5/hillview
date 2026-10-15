package cz.hillview.plugin

import kotlin.math.PI
import kotlin.math.sin
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The replay path: three stored floats back to the attitude the phone had.
 *
 * `ImuRing.KIND_RV` keeps only a unit quaternion's VECTOR PART, and the claim that this
 * loses nothing is the one worth pinning — if it were wrong, every window recorded from
 * here on would be subtly unreadable and nothing would say so.
 */
class CameraPoseQuaternionTest {

    private fun rad(deg: Float) = (deg * PI / 180.0).toFloat()

    /**
     * The same expansion with `w` SUPPLIED rather than recovered. This is the independent
     * side of the comparison below: the subject recomputes `w` from the vector part, this
     * is handed the real one.
     */
    private fun expand(w: Float, x: Float, y: Float, z: Float): FloatArray {
        val xx = 2f * x * x
        val yy = 2f * y * y
        val zz = 2f * z * z
        val xy = 2f * x * y
        val xz = 2f * x * z
        val yz = 2f * y * z
        val wx = 2f * w * x
        val wy = 2f * w * y
        val wz = 2f * w * z
        return floatArrayOf(
            1f - yy - zz, xy - wz, xz + wy,
            xy + wz, 1f - xx - zz, yz - wx,
            xz - wy, yz + wx, 1f - xx - yy,
        )
    }

    /**
     * ONE HAND-COMPUTED ANCHOR, which is what stops this file from merely being
     * self-consistent. Upright portrait facing north is +90° about the device's X axis:
     * device Y becomes world up, device Z points south, so the lens points north. Its
     * quaternion is `(cos45°, sin45°, 0, 0)` and the stored vector part is `(sin45°, 0, 0)`.
     *
     * The matrix that must come back is `[1,0,0, 0,0,-1, 0,1,0]`, and reading the pose
     * off it: `r8 = 0` so the camera is level, `atan2(r6, r7) = atan2(0, 1) = 0` so the
     * image is upright, and the lens `-(r2, r5, r8) = (0, 1, 0)` is due north. A
     * transposed or wrong-handed expansion cannot produce all four of those.
     */
    @Test
    fun uprightPortraitFacingNorthComesBackFromItsVectorPart() {
        val m = rotationMatrixFromVector(sqrt(0.5f), 0f, 0f)
        val expected = floatArrayOf(1f, 0f, 0f, 0f, 0f, -1f, 0f, 1f, 0f)
        for (i in 0..8) {
            assertEquals(expected[i], m[i], 1e-6f, "element $i")
        }
        val pose = cameraPoseFromRotationVector(sqrt(0.5f), 0f, 0f)!!
        assertEquals(0f, pose.pitchDeg, 0.01f)
        assertEquals(0f, pose.imageRollDeg, 0.01f)
        assertEquals(0f, pose.bearingDeg, 0.01f)
        assertEquals(1f, pose.determinant, 1e-4f)
        // Due north and level, so the lens is the full reference with no fallback.
        assertEquals(1f, pose.horizontalLength, 1e-4f)
        assertEquals(0f, pose.lensEast, 1e-4f)
        assertEquals(1f, pose.lensNorth, 1e-4f)
    }

    /**
     * `w` IS DETERMINED BY THE VECTOR PART, over the whole rotation group.
     *
     * A quaternion and its negation are the same rotation, so taking `w >= 0` costs
     * nothing — and it is what the platform assumes:
     * `SensorManager.getRotationMatrixFromVector` recovers `w` this very way when handed
     * a 3-element vector. The sweep is deterministic rather than random so a failure is
     * reproducible.
     */
    @Test
    fun theStoredVectorPartDeterminesTheWholeRotation() {
        var checked = 0
        var worst = 0f
        // An axis-angle sweep: every axis direction on a coarse sphere, every angle.
        for (lat in -80..80 step 20) {
            for (lon in 0 until 360 step 30) {
                for (angle in 10..350 step 20) {
                    val la = rad(lat.toFloat())
                    val lo = rad(lon.toFloat())
                    val ax = kotlin.math.cos(la) * sin(lo)
                    val ay = kotlin.math.cos(la) * kotlin.math.cos(lo)
                    val az = sin(la)
                    val h = rad(angle.toFloat()) / 2f
                    var w = kotlin.math.cos(h)
                    var x = ax * sin(h)
                    var y = ay * sin(h)
                    var z = az * sin(h)
                    // w >= 0, the canonical half of the double cover.
                    if (w < 0f) { w = -w; x = -x; y = -y; z = -z }
                    val supplied = expand(w, x, y, z)
                    val recovered = rotationMatrixFromVector(x, y, z)
                    for (i in 0..8) {
                        worst = kotlin.math.max(worst, kotlin.math.abs(supplied[i] - recovered[i]))
                    }
                    checked++
                }
            }
        }
        assertTrue(checked > 1_900, "swept only $checked rotations")
        // Float arithmetic, not an approximation: the difference is rounding alone.
        assertTrue(worst < 1e-3f, "worst matrix element difference $worst over $checked rotations")
    }

    /**
     * The precision argument behind `RV_DECIMALS = 6`, as arithmetic rather than a claim.
     *
     * `w = sqrt(1 - |v|²)` loses precision as the rotation approaches 180°, where `w` is 0
     * and the derivative is unbounded. Six decimals survive it; three — what the
     * accelerometer uses, and what this kind would have inherited — do not.
     */
    @Test
    fun sixDecimalsSurviveTheNear180DegreeCase() {
        val h = rad(179.9f) / 2f
        val c = sin(h) / sqrt(3f)
        val exact = cameraPoseFromRotationVector(c, c, c)!!

        fun rounded(decimals: Int): CameraPose {
            val f = Math.pow(10.0, decimals.toDouble()).toFloat()
            val r = Math.round(c * f) / f
            return cameraPoseFromRotationVector(r, r, r)!!
        }
        assertTrue(
            degreesClose(exact.imageRollDeg, rounded(6).imageRollDeg, 0.5f),
            "6 decimals moved the roll from ${exact.imageRollDeg} to ${rounded(6).imageRollDeg}",
        )
        assertTrue(
            !degreesClose(exact.imageRollDeg, rounded(3).imageRollDeg, 0.5f),
            "3 decimals were fine after all (${exact.imageRollDeg} vs " +
                "${rounded(3).imageRollDeg}) — then RV_DECIMALS has no justification",
        )
    }
}
