package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The location gate on the shutter. The web app asserts "implies
 * cameraReady && locationData"; the lift exists because the requirement is
 * hand-holding for first-time users, not physics — someone underground can
 * position the map manually and shoot against that.
 */
class ShutterGateTest {

    @Test
    fun noFixMeansNoShutter() {
        assertFalse(shutterEnabled(ready = true, hasFix = false, manualLocationArmed = false))
    }

    @Test
    fun aFixOpensTheGate() {
        assertTrue(shutterEnabled(ready = true, hasFix = true, manualLocationArmed = false))
    }

    @Test
    fun liftingTheGateOpensItWithoutAFix() {
        assertTrue(shutterEnabled(ready = true, hasFix = false, manualLocationArmed = true))
    }

    @Test
    fun nothingOpensAGateOnAnUnreadyCamera() {
        assertFalse(shutterEnabled(ready = false, hasFix = true, manualLocationArmed = true))
    }
}
