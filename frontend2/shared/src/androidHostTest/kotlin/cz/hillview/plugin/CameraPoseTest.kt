package cz.hillview.plugin

import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The orientation maths that replaced `remapCoordinateSystem` + `getOrientation` + two
 * `if (abs(roll) > 90)` branches.
 *
 * Every case is built the same way: name the three DEVICE axes in world coordinates,
 * assemble them as the matrix's columns, and assert what the lens is doing. That is the
 * opposite direction from the code under test, so a sign error cannot cancel out.
 *
 * The cases are the ones real captures got wrong on 2026-10-03: the same lens direction
 * reported in portrait, at 40° of roll and in landscape, and an up/level/down sweep held
 * in landscape.
 */
class CameraPoseTest {

    /**
     * A row-major device→world matrix from the device axes, each given in world
     * coordinates as (east, north, up). The matrix's COLUMNS are those axes, because
     * it maps device vectors to world ones.
     */
    private fun matrix(
        dx: Triple<Float, Float, Float>,
        dy: Triple<Float, Float, Float>,
        dz: Triple<Float, Float, Float>,
    ) = floatArrayOf(
        dx.first, dy.first, dz.first,
        dx.second, dy.second, dz.second,
        dx.third, dy.third, dz.third,
    )

    private val east = Triple(1f, 0f, 0f)
    private val north = Triple(0f, 1f, 0f)
    private val up = Triple(0f, 0f, 1f)
    private val down = Triple(0f, 0f, -1f)
    private val south = Triple(0f, -1f, 0f)

    private fun pose(r: FloatArray) = cameraPoseFromRotationMatrix(r)!!

    // --- the lens direction must not depend on how the phone is rolled ---

    /** Portrait, upright, lens level and facing north. The reference. */
    @Test
    fun portraitUprightFacingNorth() {
        val p = pose(matrix(dx = east, dy = up, dz = south))
        assertEquals(0f, p.bearingDeg, 0.01f)
        assertEquals(0f, p.pitchDeg, 0.01f)
        assertEquals(0f, p.imageRollDeg, 0.01f)
        assertEquals(1f, p.horizontalLength, 0.01f)
    }

    /**
     * THE BUG, as a test. Same lens direction, phone rotated 90° about the optical
     * axis. Real captures put portrait at 273.1° and landscape at 272.1° — 1° apart,
     * which is what told us there is no inherent landscape bias — while the published
     * pitch/roll were unusable. Here the bearing must be IDENTICAL and only the image
     * roll may move.
     */
    @Test
    fun landscapeReportsTheSameBearingAsPortrait() {
        val p = pose(matrix(dx = down, dy = east, dz = south))
        assertEquals(0f, p.bearingDeg, 0.01f)
        assertEquals(0f, p.pitchDeg, 0.01f)
        assertEquals(-90f, p.imageRollDeg, 0.01f)
    }

    /**
     * THE OTHER HALF OF THE BUG. Three deliberate ~40° captures came out 43–52° off
     * their own un-rolled neighbours, because the orientation classifier still called
     * them PORTRAIT and applied the portrait remap to a rolled phone. There is no
     * classifier here, so the bearing cannot care.
     */
    @Test
    fun aPartlyRolledPhoneStillKnowsWhereTheLensPoints() {
        for (rollDeg in listOf(10f, 38f, 45f, 60f, 89f)) {
            val a = Math.toRadians(rollDeg.toDouble()).toFloat()
            val p = pose(
                matrix(
                    dx = Triple(cos(a), 0f, -sin(a)),
                    dy = Triple(sin(a), 0f, cos(a)),
                    dz = south,
                ),
            )
            assertEquals(0f, p.bearingDeg, 0.02f, "bearing moved at ${rollDeg}° of roll")
            assertEquals(0f, p.pitchDeg, 0.02f, "pitch moved at ${rollDeg}° of roll")
            assertEquals(-rollDeg, p.imageRollDeg, 0.02f)
        }
    }

    // --- elevation, in both orientations ---

    /** Portrait, lens 30° below the horizon. Positive pitch IS down — the app's sign. */
    @Test
    fun pitchIsPositiveLookingDown() {
        val c = cos(Math.toRadians(30.0)).toFloat()
        val s = sin(Math.toRadians(30.0)).toFloat()
        val p = pose(matrix(dx = east, dy = Triple(0f, s, c), dz = Triple(0f, -c, s)))
        assertEquals(0f, p.bearingDeg, 0.01f)
        assertEquals(30f, p.pitchDeg, 0.01f)
        assertEquals(0f, p.imageRollDeg, 0.01f)
    }

    /**
     * THE SWEEP THAT BROKE THE OLD CODE. Up / level / down, held in landscape. The
     * published `pitch_deg` came back −56.7 / −84.4 / −68.0 — not even monotonic —
     * where gravity said −33.7 / −4.4 / +21.8, and `roll_deg` flipped 180° partway
     * through. Here pitch must track the lens and the image roll must hold still.
     */
    @Test
    fun anUpLevelDownSweepInLandscapeIsMonotonic() {
        val pitches = listOf(-35f, -5f, 0f, 20f, 40f)
        val got = pitches.map { want ->
            val a = Math.toRadians(-want.toDouble()).toFloat()   // elevation = -pitch
            val c = cos(a)
            val s = sin(a)
            // Lens at that elevation facing north; phone rolled 90° so screen-up is
            // east. The lens points along (0, cos e, sin e), so device -Z is its
            // negation and device X closes the right-handed frame as dy × dz.
            val p = pose(
                matrix(
                    dx = Triple(0f, s, -c),
                    dy = east,
                    dz = Triple(0f, -c, -s),
                ),
            )
            assertEquals(0f, p.bearingDeg, 0.02f, "bearing moved at pitch $want")
            assertEquals(-90f, p.imageRollDeg, 0.02f, "image roll moved at pitch $want")
            p.pitchDeg
        }
        got.zip(pitches).forEach { (g, want) -> assertEquals(want, g, 0.02f) }
        assertEquals(got.sorted(), got, "pitch must be monotonic across the sweep")
    }

    // --- the degeneracy, named instead of hidden ---

    /**
     * A lens pointed straight down has no bearing, and `atan2(0, 0)` returns 0 — so an
     * unguarded caller publishes "due north" for a photo of the pavement.
     * [CameraPose.horizontalLength] is how that is visible rather than silent.
     */
    @Test
    fun aVerticalLensReportsThatItHasNoBearing() {
        val straightDown = pose(matrix(dx = east, dy = north, dz = up))
        assertEquals(90f, straightDown.pitchDeg, 0.01f)
        assertEquals(0f, straightDown.horizontalLength, 0.01f)
        assertTrue(!straightDown.bearingIsDefined())

        val straightUp = pose(matrix(dx = east, dy = south, dz = down))
        assertEquals(-90f, straightUp.pitchDeg, 0.01f)
        assertTrue(!straightUp.bearingIsDefined())
    }

    /** ...and a level lens is as well-conditioned as it gets. */
    @Test
    fun aLevelLensIsFullyConditioned() {
        val p = pose(matrix(dx = east, dy = up, dz = south))
        assertTrue(p.bearingIsDefined())
        assertEquals(1f, p.horizontalLength, 0.001f)
    }

    /**
     * Before the first sample the service's matrix is all zeros. Returning a pose there
     * would read as a level camera facing north — a plausible lie, which is worse than
     * no answer.
     */
    @Test
    fun aMatrixThatIsNotOneYieldsNoPose() {
        assertNull(cameraPoseFromRotationMatrix(FloatArray(9)))
        assertNull(cameraPoseFromRotationMatrix(FloatArray(4)))
        assertNull(cameraPoseFromRotationMatrix(floatArrayOf(0f, 0f, 9f, 0f, 0f, 0f, 0f, 0f, 0f)))
    }

    // --- the tie to the measurement that found the bug ---

    /**
     * `pitchDeg` and `imageRollDeg` must equal the GRAVITY-derived values, because that
     * is the independent reference the whole diagnosis rests on: world up expressed in
     * device coordinates is the matrix's third row, and Android's gravity vector points
     * along it. Portrait captures already agree to ≤0.8° in prod; this pins the identity
     * exactly, for every pose.
     */
    @Test
    fun pitchAndRollAgreeWithTheGravityVector() {
        val cases = listOf(
            matrix(dx = east, dy = up, dz = south),
            matrix(dx = down, dy = east, dz = south),
            matrix(dx = Triple(0f, -0.5f, -0.866f), dy = east, dz = Triple(0f, -0.866f, 0.5f)),
            matrix(dx = east, dy = north, dz = up),
        )
        for (r in cases) {
            val p = pose(r)
            // Gravity as Android reports it: along world up, in device coordinates.
            val gx = r[6]
            val gy = r[7]
            val gz = r[8]
            val n = kotlin.math.sqrt(gx * gx + gy * gy + gz * gz)
            val pitchFromGravity = Math.toDegrees(asin((gz / n).coerceIn(-1f, 1f).toDouble())).toFloat()
            val rollFromGravity = Math.toDegrees(atan2(gx, gy).toDouble()).toFloat()
            assertEquals(pitchFromGravity, p.pitchDeg, 0.02f)
            assertEquals(rollFromGravity, p.imageRollDeg, 0.02f)
        }
    }

    @Test
    fun theDegreeDeltaIsWraparoundSafe() {
        assertEquals(20f, signedDegreeDelta(350f, 10f), 0.001f)
        assertEquals(-20f, signedDegreeDelta(10f, 350f), 0.001f)
        assertEquals(180f, signedDegreeDelta(0f, 180f), 0.001f)
        assertTrue(degreesClose(359f, 1f, 3f))
        assertTrue(!degreesClose(0f, 90f, 3f))
    }
}
