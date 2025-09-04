package cz.hillview.plugin

import org.junit.Test
import org.junit.Assert.*
import org.junit.Before
import kotlin.math.*

class MadgwickAHRSTest {
    private lateinit var madgwick: MadgwickAHRS
    private val epsilon = 0.001f // Tolerance for floating-point comparisons

    @Before
    fun setUp() {
        madgwick = MadgwickAHRS(sampleFreq = 100f, beta = 0.1f)
    }

    @Test
    fun testInitialQuaternionIsIdentity() {
        // After creation, quaternion should be [1, 0, 0, 0]
        val angles = madgwick.getEulerAngles()
        assertEquals(0f, angles.first, epsilon) // Yaw
        assertEquals(0f, angles.second, epsilon) // Pitch
        assertEquals(0f, angles.third, epsilon) // Roll
    }

    @Test
    fun testResetQuaternion() {
        // Update with some values
        madgwick.updateIMU(0.1f, 0.2f, 0.3f, 0f, 0f, 1f)

        // Reset
        madgwick.reset()

        // Should be back to identity
        val angles = madgwick.getEulerAngles()
        assertEquals(0f, angles.first, epsilon)
        assertEquals(0f, angles.second, epsilon)
        assertEquals(0f, angles.third, epsilon)
    }

    @Test
    fun testUpdateIMUWithZeroGyro() {
        // With zero gyroscope values and gravity pointing down, should remain stable
        for (i in 1..10) {
            madgwick.updateIMU(0f, 0f, 0f, 0f, 0f, 1f)
        }

        val angles = madgwick.getEulerAngles()
        assertEquals(0f, angles.first, epsilon)
        assertEquals(0f, angles.second, epsilon)
        assertEquals(0f, angles.third, epsilon)
    }

    @Test
    fun testUpdateIMUWithZeroAccelerometer() {
        // With zero accelerometer values, only gyroscope integration should occur
        madgwick.updateIMU(0.1f, 0f, 0f, 0f, 0f, 0f)

        val angles = madgwick.getEulerAngles()
        // Should have some rotation due to gyroscope
        assertTrue(abs(angles.first) > 0 || abs(angles.second) > 0 || abs(angles.third) > 0)
    }

    @Test
    fun testUpdateWithAllSensors() {
        // Test full sensor fusion with gyro, accel, and mag
        madgwick.update(
            0.1f, 0.2f, 0.3f,  // Gyroscope (rad/s)
            0f, 0f, 1f,         // Accelerometer (g)
            0.4f, 0f, 0.3f      // Magnetometer (normalized)
        )

        val angles = madgwick.getEulerAngles()
        // Should produce some orientation change
        assertTrue(abs(angles.first) > 0 || abs(angles.second) > 0 || abs(angles.third) > 0)
    }

    @Test
    fun testUpdateWithZeroMagnetometer() {
        // With zero magnetometer values, should still work with gyro and accel
        madgwick.update(
            0.1f, 0f, 0f,       // Gyroscope
            0f, 0f, 1f,         // Accelerometer
            0f, 0f, 0f          // Magnetometer (all zeros)
        )

        // Should still produce valid output
        val angles = madgwick.getEulerAngles()
        assertFalse(angles.first.isNaN())
        assertFalse(angles.second.isNaN())
        assertFalse(angles.third.isNaN())
    }

    @Test
    fun testGimbalLockDetection() {
        // Force gimbal lock condition by manipulating quaternion
        // This is a bit hacky but tests the gimbal lock detection
        val gimbalMadgwick = MadgwickAHRS()

        // Apply strong pitch rotations to approach gimbal lock
        for (i in 1..100) {
            gimbalMadgwick.updateIMU(0f, 5f, 0f, 0f, 0f, 1f)
        }

        val angles = gimbalMadgwick.getEulerAngles()
        // Pitch should be clamped at ±90 degrees (±π/2 radians)
        assertTrue(abs(angles.second) <= PI/2 + epsilon)
    }

    @Test
    fun testSetGain() {
        val newBeta = 0.2f
        madgwick.setGain(newBeta)

        // Update with same values but different gain
        madgwick.updateIMU(0.1f, 0.1f, 0.1f, 0f, 0f, 1f)
        val angles1 = madgwick.getEulerAngles()

        // Reset and try with original gain
        madgwick.reset()
        madgwick.setGain(0.1f)
        madgwick.updateIMU(0.1f, 0.1f, 0.1f, 0f, 0f, 1f)
        val angles2 = madgwick.getEulerAngles()

        // Results should be different due to different gains
        assertTrue(
            abs(angles1.first - angles2.first) > epsilon ||
            abs(angles1.second - angles2.second) > epsilon ||
            abs(angles1.third - angles2.third) > epsilon
        )
    }

    @Test
    fun testSetSampleFrequency() {
        val newFreq = 200f
        madgwick.setSampleFrequency(newFreq)

        // Update with same values but different frequency
        madgwick.updateIMU(1f, 0f, 0f, 0f, 0f, 1f)
        val angles1 = madgwick.getEulerAngles()

        // Reset and try with different frequency
        madgwick.reset()
        madgwick.setSampleFrequency(50f)
        madgwick.updateIMU(1f, 0f, 0f, 0f, 0f, 1f)
        val angles2 = madgwick.getEulerAngles()

        // Results should be different due to different integration time steps
        assertTrue(
            abs(angles1.first - angles2.first) > epsilon ||
            abs(angles1.second - angles2.second) > epsilon ||
            abs(angles1.third - angles2.third) > epsilon
        )
    }

    @Test
    fun testQuaternionNormalization() {
        // Apply many updates to test quaternion remains normalized
        for (i in 1..100) {
            madgwick.updateIMU(
                0.1f * sin(i * 0.1f),
                0.2f * cos(i * 0.1f),
                0.15f,
                0f,
                0f,
                1f
            )
        }

        // Get angles - if quaternion is not normalized, this will fail
        val angles = madgwick.getEulerAngles()
        assertFalse(angles.first.isNaN())
        assertFalse(angles.second.isNaN())
        assertFalse(angles.third.isNaN())

        // Angles should be within valid ranges
        assertTrue(abs(angles.first) <= PI + epsilon)
        assertTrue(abs(angles.second) <= PI/2 + epsilon)
        assertTrue(abs(angles.third) <= PI + epsilon)
    }

    @Test
    fun testConsistentOrientationTracking() {
        // Test that multiple small rotations equal one large rotation
        val madgwick1 = MadgwickAHRS()
        val madgwick2 = MadgwickAHRS()

        // Apply one large rotation to madgwick1
        madgwick1.updateIMU(1f, 0f, 0f, 0f, 0f, 1f)

        // Apply 10 small rotations to madgwick2
        for (i in 1..10) {
            madgwick2.updateIMU(0.1f, 0f, 0f, 0f, 0f, 1f)
        }

        val angles1 = madgwick1.getEulerAngles()
        val angles2 = madgwick2.getEulerAngles()

        // Should be approximately equal
        assertEquals(angles1.first, angles2.first, 0.01f)
        assertEquals(angles1.second, angles2.second, 0.01f)
        assertEquals(angles1.third, angles2.third, 0.01f)
    }

    @Test
    fun testStabilityWithNoisyData() {
        // Test algorithm stability with noisy sensor data
        val noiseLevel = 0.01f
        var previousAngles = madgwick.getEulerAngles()

        for (i in 1..50) {
            // Add small noise to sensor readings
            madgwick.updateIMU(
                0f + (Math.random().toFloat() - 0.5f) * noiseLevel,
                0f + (Math.random().toFloat() - 0.5f) * noiseLevel,
                0f + (Math.random().toFloat() - 0.5f) * noiseLevel,
                0f + (Math.random().toFloat() - 0.5f) * noiseLevel,
                0f + (Math.random().toFloat() - 0.5f) * noiseLevel,
                1f + (Math.random().toFloat() - 0.5f) * noiseLevel
            )

            val currentAngles = madgwick.getEulerAngles()

            // Changes should be small
            assertTrue(abs(currentAngles.first - previousAngles.first) < 0.1f)
            assertTrue(abs(currentAngles.second - previousAngles.second) < 0.1f)
            assertTrue(abs(currentAngles.third - previousAngles.third) < 0.1f)

            previousAngles = currentAngles
        }
    }
}
