package cz.hillview.geo

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The declination one-shots' schedule, and the config that asks for them
 * (user, 2026-10-11: "logic that just ensures that the oldest fix is no older
 * than some reasonable value").
 */
class DeclinationFixTest {

    private val maxAge = DECLINATION_FIX_MAX_AGE_MS

    @Test
    fun aFreshFixIsAskedForAgainWhenItReachesTheLimit() {
        assertEquals(maxAge, nextDeclinationFixInMs(fixAgeMs = 0, maxAge))
    }

    @Test
    fun aCachedAnswerIsAskedForAgainWhenItReachesTheLimitNotAFullPeriodLater() {
        // The platform answered from a 25-minute-old cache: five minutes left.
        assertEquals(5 * 60_000L, nextDeclinationFixInMs(fixAgeMs = 25 * 60_000L, maxAge))
    }

    @Test
    fun anAnswerAtTheLimitCannotMakeThemSpin() {
        assertEquals(DECLINATION_FIX_MIN_GAP_MS, nextDeclinationFixInMs(fixAgeMs = maxAge - 1_000, maxAge))
        assertEquals(DECLINATION_FIX_MIN_GAP_MS, nextDeclinationFixInMs(fixAgeMs = maxAge + 60_000, maxAge))
    }

    @Test
    fun noAnswerIsRetriedSooner() {
        assertEquals(DECLINATION_FIX_RETRY_MS, nextDeclinationFixInMs(fixAgeMs = null, maxAge))
        assertTrue(DECLINATION_FIX_RETRY_MS < maxAge)
    }

    @Test
    fun aFixFromTheFutureIsNotAskedForLater() {
        // Clock skew between the fix's stamp and ours: never past the limit.
        assertEquals(maxAge, nextDeclinationFixInMs(fixAgeMs = -5_000, maxAge))
    }

    @Test
    fun theCompassAloneRunsNoStreamOnlyTheOneShots() {
        val c = compassOnlyGeoConfig()
        assertEquals(0L, c.locationIntervalMs)
        assertEquals(30 * 60_000L, c.declinationFixMaxAgeMs)
        assertTrue(c.sensors)
        assertEquals(mapOnlyGeoConfig().sensorDelayUs, c.sensorDelayUs, "the same compass as map viewing")
    }

    @Test
    fun everythingThatWantsFixesStillRunsTheStream() {
        for (c in listOf(mapOnlyGeoConfig(), captureGeoConfig(), externalCameraConfig())) {
            assertTrue(c.locationIntervalMs > 0, "$c")
        }
    }
}
