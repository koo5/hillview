package cz.hillview.capture

import cz.hillview.map.BearingState
import cz.hillview.map.DeviceAttitude
import cz.hillview.map.DeviceMotionSample
import cz.hillview.map.MapStateHolder
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class CapturePitchTest {
    private val atMs = 1_700_000_000_000L

    private fun attitude(pitch: Double) = DeviceAttitude(
        trueDeg = 90.0, magneticDeg = 86.0, pitch = pitch, roll = 0.0, ts = atMs,
    )

    @Test
    fun aVerticalSweepUsesTheNewPoseWhileTheHeadingStaysFixed() {
        val map = MapStateHolder(initialBearing = BearingState(bearing = 90.0, pitch = 0.0))
        for (pitch in listOf(-25.0, 0.0, 25.0)) {
            map.updateDeviceAttitude(attitude(pitch))
            val bearing = map.bearing.value
            val shot = SensorSnapshot(
                capturedAtMs = atMs,
                trueBearingDeg = bearing.bearing.toFloat(),
                pitchDeg = bearing.pitch?.toFloat(),
                attitude = map.deviceAttitude.value,
            )
            assertEquals(90.0f, shot.trueBearingDeg)
            assertEquals(0.0, map.bearing.value.pitch)
            assertEquals(pitch, shot.measuredPitchDeg())
        }
    }

    @Test
    fun gravityWinsOverBothTheElectedPitchAndTheAttitudeAngles() {
        val shot = SensorSnapshot(
            capturedAtMs = atMs,
            pitchDeg = 0f,
            attitude = attitude(5.0),
            // looking-up-23.4 in the backend's shared pose fixture.
            motion = DeviceMotionSample(gravity = listOf(0f, 9.000098f, -3.894690f), atMs = atMs),
        )
        assertEquals(23.4, shot.measuredPitchDeg()!!, 0.001)
    }

    @Test
    fun theCompletedSnapshotUsesTheExposurePoseInsteadOfThePressPose() {
        val press = SensorSnapshot(capturedAtMs = atMs, attitude = attitude(-25.0))
        val saved = press.copy(attitude = attitude(25.0))
        assertEquals(-25.0, press.measuredPitchDeg())
        assertEquals(25.0, saved.measuredPitchDeg())
    }

    @Test
    fun aBearingAloneCannotInventThePitchOfAnUnmeasuredShot() {
        assertNull(SensorSnapshot(capturedAtMs = atMs, pitchDeg = 12f).measuredPitchDeg())
    }

    @Test
    fun invalidGravityFallsBackToTheMeasuredAttitude() {
        for (gravity in listOf(emptyList(), listOf(0f, 0f), listOf(0f, 0f, 0f), listOf(Float.NaN, 9f, 0f))) {
            val shot = SensorSnapshot(
                capturedAtMs = atMs,
                attitude = attitude(-6.5),
                motion = DeviceMotionSample(gravity = gravity, atMs = atMs),
            )
            assertEquals(-6.5, shot.measuredPitchDeg())
            assertNull(shot.copy(attitude = null).measuredPitchDeg())
        }
    }

    @Test
    fun aLevelShotIsZeroAndNotNegativeZero() {
        val shot = SensorSnapshot(
            capturedAtMs = atMs,
            motion = DeviceMotionSample(gravity = listOf(0f, 9.80665f, 0f), atMs = atMs),
        )
        assertEquals("0.0", shot.measuredPitchDeg().toString())
    }
}
