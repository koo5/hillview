package cz.hillview.geo

import android.Manifest
import android.location.LocationManager
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The walking compass alone gets a position for its declination from one
 * fused request, and the fix stream stays off (user, 2026-10-11). Drives the
 * real engine against the real fused provider: whether getCurrentLocation
 * answers at all, with which settings, is the thing a host test cannot know.
 */
@RunWith(AndroidJUnit4::class)
class DeclinationFixDeviceTest {

    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private val context get() = instrumentation.targetContext

    @Test
    fun theCompassAloneGetsItsDeclinationWithoutTheFixStream() {
        instrumentation.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.ACCESS_FINE_LOCATION)
        instrumentation.uiAutomation.grantRuntimePermission(context.packageName, Manifest.permission.ACCESS_COARSE_LOCATION)
        val locationManager = context.getSystemService(LocationManager::class.java)
        assumeTrue("location is switched off on this device", locationManager.isLocationEnabled)

        // The engine asks only in the foreground, as in the app.
        ActivityScenario.launch(ComponentActivity::class.java).use {
            val engine = GeoEngine.get(context)
            engine.configure(compassOnlyGeoConfig(), OWNER_ACTIVITY)
            try {
                val deadline = SystemClock.elapsedRealtime() + 45_000
                while (engine.declinationFixAgeMs() == null && SystemClock.elapsedRealtime() < deadline) {
                    Thread.sleep(250)
                }
                val ageMs = engine.declinationFixAgeMs()
                println("declination one-shot: ${engine.livenessLine()}")
                assertNotNull(ageMs, "no declination fix within 45 s — ${engine.livenessLine()}")
                assertTrue(ageMs <= DECLINATION_FIX_MAX_AGE_MS, "the fix is ${ageMs / 1000}s old")
                assertFalse(engine.locationActive.value, "the fix stream ran for the compass alone")
            } finally {
                engine.configure(GeoConfig.Off, OWNER_ACTIVITY)
            }
        }
    }
}
