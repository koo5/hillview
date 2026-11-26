package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/** The travel arrow's direction, and when there is one to show. */
class TravelBearingTest {

    @Test
    fun itIsTheArrowWithTheOffsetTakenOut() {
        assertEquals(20.0, travelBearingFor(true, TrackingPhase.Active, bearingDeg = 80.0, mountOffsetDeg = 60.0))
    }

    @Test
    fun itWrapsThroughNorth() {
        assertEquals(350.0, travelBearingFor(true, TrackingPhase.Active, bearingDeg = 10.0, mountOffsetDeg = 20.0))
        assertEquals(10.0, travelBearingFor(true, TrackingPhase.Active, bearingDeg = 350.0, mountOffsetDeg = 340.0))
    }

    @Test
    fun anOffsetDragKeepsItWhereItWas() {
        // The drag turns the arrow and the offset by the same angle.
        val before = travelBearingFor(true, TrackingPhase.Active, 80.0, 60.0)
        val after = travelBearingFor(true, TrackingPhase.Active, normalizeBearing(80.0 + 300.0), normalizeBearing(60.0 + 300.0))
        assertEquals(before, after)
    }

    @Test
    fun beforeCarModeHasWrittenAHeadingThereIsNone() {
        for (phase in listOf(TrackingPhase.Inactive, TrackingPhase.Starting, TrackingPhase.Error)) {
            assertNull(travelBearingFor(true, phase, 80.0, 60.0), "$phase")
        }
    }

    @Test
    fun outsideAMountOffsetDragThereIsNone() {
        assertNull(travelBearingFor(false, TrackingPhase.Active, 80.0, 60.0))
    }
}
