package cz.hillview

import android.os.SystemClock
import android.util.Log
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.settings.UploadSettingsRepository
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * The capture-burst upload storm — the port of upload-coalescing.test.ts.
 *
 * The machinery under test is shared-kt's PhotoUploadManager/Worker,
 * compiled verbatim into this app: a burst of N captures must collapse into
 * at most one immediate (expedited) worker run plus one deferred 15 s batch
 * run per window — never one worker per photo — and a foreground app must
 * never promote to a foreground service (the promotion churned the main
 * thread and crashed via ForegroundServiceDidNotStartInTime before the fix).
 *
 * Same observation channel as the original: the marker log lines added
 * alongside the fix, read from logcat. No login is needed — a drain without
 * an auth token stops cleanly (no retry backoff), which keeps the run count
 * exactly the coalescing arithmetic.
 */
@RunWith(AndroidJUnit4::class)
class UploadCoalescingBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val gps = MockGps()

    private val settingsRepo: UploadSettingsRepository
        get() = GlobalContext.get().get()

    @Before
    fun armAutoUpload() {
        gps.install()
        // startAutomaticUpload is a no-op with auto-upload off, so the burst
        // can only be observed with it on. Through the repository (not raw
        // prefs) so the screen's StateFlow agrees and the prompt stays away;
        // the licence must be set first — the consent chain the settings UI
        // enforces (the switch is inert until a licence is accepted).
        settingsRepo.update {
            it.copy(
                license = it.license ?: cz.hillview.settings.ALLOWED_LICENSES.first(),
                autoUploadEnabled = true,
                wifiOnly = false,
            )
        }
    }

    @After
    fun disarmAutoUpload() {
        // Back to the privacy default. Already-queued batch runs are left to
        // fire: without an auth token they no-op, same as in the app.
        settingsRepo.update { it.copy(autoUploadEnabled = false) }
        gps.remove()
    }

    @Test
    fun captureBurstCoalescesIntoFewRunsAndNeverPromotesInForeground() {
        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()

        Behaviour.shell("logcat -c")
        val dao = Behaviour.photoDao()
        val before = dao.getTotalPhotoCount()
        val burstStart = SystemClock.elapsedRealtime()

        val burst = 5
        repeat(burst) { i ->
            compose.waitUntil(15_000) { compose.shutterIsEnabled() }
            // The half-height capture pane scrolls its controls — an
            // offscreen node's click coordinate would land on the map.
            runCatching { compose.onNodeWithTag("capture-shutter").performScrollTo() }
            compose.onNodeWithTag("capture-shutter").performClick()
            // Each save must land before the next shot — the per-save trigger
            // fires from the save, and the run count is only meaningful if
            // every trigger actually happened.
            compose.waitUntil(30_000) { dao.getTotalPhotoCount() >= before + i + 1 }
        }
        val burstMs = SystemClock.elapsedRealtime() - burstStart
        // The last enqueue trails its DB row by an IO hop.
        SystemClock.sleep(1_000)

        // Wait the deferred batch out: it fires 15 s after its window opened.
        fun count(log: String, needle: String) = log.lineSequence().count { it.contains(needle) }
        var log = Behaviour.shell("logcat -d")
        val deadline = SystemClock.elapsedRealtime() + 40_000
        while (SystemClock.elapsedRealtime() < deadline && count(log, "Starting upload work") < 2) {
            SystemClock.sleep(2_000)
            log = Behaviour.shell("logcat -d")
        }

        val enqueues = count(log, "enqueue photo_upload")
        val runs = count(log, "Starting upload work")
        val promotions = count(log, "promoted to foreground")
        val backgroundedRuns = count(log, "promote decision: backgrounded=true")
        val fgsCrashes = count(log, "ForegroundServiceDidNotStartInTimeException")
        Log.i(
            "UploadCoalescing",
            "captured=$burst burstMs=$burstMs enqueues=$enqueues runs=$runs " +
                "promotions=$promotions backgroundedRuns=$backgroundedRuns",
        )

        // Correctness: every capture landed.
        assertEquals(burst, dao.getTotalPhotoCount() - before)

        // The crash class is gone, and a foreground app never promotes.
        assertEquals(0, fgsCrashes)
        assertEquals("promoted while foreground", 0, promotions)
        assertEquals(0, backgroundedRuns)

        // The per-save triggers all fired (the test isn't vacuous)...
        assertTrue("per-save triggers missing: enqueues=$enqueues", enqueues >= burst)
        // ...and coalescing collapsed them: at most one immediate + one batch
        // run per 15 s window the burst spanned. A regression to per-photo
        // workers shows up as ~$burst runs and fails both bounds.
        val windows = (burstMs / 15_000L).toInt() + 1
        assertTrue("runs=$runs across $windows window(s)", runs in 1..(windows * 2))
        assertTrue("no coalescing: runs=$runs enqueues=$enqueues", runs < enqueues)

        // The original's responsiveness proxy: the screen is still alive
        // (scrolling it back into view IS interaction).
        compose.onNodeWithTag("capture-status").performScrollTo().assertIsDisplayed()
    }
}
