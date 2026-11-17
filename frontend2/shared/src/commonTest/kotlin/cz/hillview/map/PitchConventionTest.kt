package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The boundary where pitch changes sign, pinned in both directions.
 *
 * The functions are a negation, so there is little arithmetic to get wrong. What
 * there is to get wrong is the DIRECTION, and these cases are written in terms of a
 * pose rather than of numbers so that reading them says which way is which.
 */
class PitchConventionTest {

    /**
     * The anchor measurement, from docs/recon-capture-metadata.md: a level portrait
     * capture with the lens 4.6° above the horizon reads −4.5 off the sensor.
     */
    @Test
    fun aLensAboveTheHorizonIsNegativeOnTheSensorAndPositiveInTheState() {
        assertEquals(4.5, statePitchFromSensor(-4.5))
        assertEquals(-4.5, sensorPitchFromState(4.5))
    }

    @Test
    fun aLensBelowTheHorizonIsTheOtherWayRound() {
        assertEquals(-11.0, statePitchFromSensor(11.0))
        assertEquals(11.0, sensorPitchFromState(-11.0))
    }

    /**
     * Level is level, and must not come back as NEGATIVE zero.
     *
     * Kotlin prints `-0.0` as "-0.0", so a plain negation puts that in the
     * bearings table, in the capture stamp and in the exported CSV for a phone
     * that was exactly level. This assertion was first written as
     * `statePitchFromSensor(0.0) + 0.0`, which hides the very thing it is for.
     */
    @Test
    fun levelStaysLevelAndNeverBecomesNegativeZero() {
        assertEquals("0.0", statePitchFromSensor(0.0).toString())
        assertEquals("0.0", sensorPitchFromState(0.0).toString())
    }

    /**
     * The round trip is what the stamp relies on: the state converts in, the stamp
     * converts back, and `capture_pose` then negates once more to reach the server's
     * positive-up `photos.pitch`. Two of those three are here.
     */
    @Test
    fun theRoundTripIsTheIdentity() {
        listOf(-90.0, -4.5, 0.0, 7.25, 90.0).forEach {
            assertEquals(it, sensorPitchFromState(statePitchFromSensor(it)))
            assertEquals(it, statePitchFromSensor(sensorPitchFromState(it)))
        }
    }
}
