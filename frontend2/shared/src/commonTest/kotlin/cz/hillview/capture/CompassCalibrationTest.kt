package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The calibration trigger from hints.svelte.ts, pinned: walking mode AND a
 * known below-HIGH magnetometer status.
 */
class NeedsCompassCalibrationTest {

    @Test
    fun lowAccuracyInWalkingModeAsksForCalibration() {
        assertTrue(needsCompassCalibration(walkingMode = true, accuracyLevel = 1))
        assertTrue(needsCompassCalibration(walkingMode = true, accuracyLevel = 0))
        assertTrue(needsCompassCalibration(walkingMode = true, accuracyLevel = 2))
    }

    @Test
    fun highAccuracyNeverDoes() {
        assertFalse(needsCompassCalibration(walkingMode = true, accuracyLevel = 3))
    }

    @Test
    fun carModeNeverDoes() {
        // Car mode bearings come from GPS travel; shaking the phone in a
        // figure-8 while driving helps nobody.
        assertFalse(needsCompassCalibration(walkingMode = false, accuracyLevel = 0))
    }

    @Test
    fun anUnknownStatusDoesNotNag() {
        // null = no reading yet, -1 = the sensor service's initial value.
        assertFalse(needsCompassCalibration(walkingMode = true, accuracyLevel = null))
        assertFalse(needsCompassCalibration(walkingMode = true, accuracyLevel = -1))
    }

    @Test
    fun labelsMatchTheOriginalsWording() {
        assertEquals("HIGH", compassAccuracyLabel(3))
        assertEquals("MEDIUM", compassAccuracyLabel(2))
        assertEquals("LOW", compassAccuracyLabel(1))
        assertEquals("UNRELIABLE", compassAccuracyLabel(0))
        assertEquals("UNKNOWN", compassAccuracyLabel(null))
        assertEquals("UNKNOWN", compassAccuracyLabel(-1))
    }
}
