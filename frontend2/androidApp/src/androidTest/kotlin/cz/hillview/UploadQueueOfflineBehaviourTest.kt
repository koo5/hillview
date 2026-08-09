package cz.hillview

import android.os.SystemClock
import android.util.Log
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.auth.SessionManager
import cz.hillview.settings.ALLOWED_LICENSES
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * The offline upload queue — the port of upload-queue-offline.test.ts: a
 * photo captured with no connectivity must sit in the Room queue (the
 * WorkManager drain parked on its CONNECTED constraint) and drain on its
 * own once the network returns.
 *
 * Needs the dev backend at 10.0.2.2:8055 and a real login (test /
 * StrongTestPassword123!, recreated through the backend's debug endpoint).
 * When the backend is down the test SKIPS (Assume) rather than failing —
 * the rest of this suite is deliberately backend-free.
 *
 * Server ack is asserted from the app's own record (serverPhotoId /
 * uploadStatus on the Room row) — the Appium original polled the backend's
 * photo list from the host, which an on-device test does not need.
 */
@RunWith(AndroidJUnit4::class)
class UploadQueueOfflineBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
        android.Manifest.permission.POST_NOTIFICATIONS,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val gps = MockGps()

    private fun setNetwork(on: Boolean) {
        val arg = if (on) "enable" else "disable"
        // Both radios: the emulator NATs 10.0.2.2 through wifi AND cellular.
        Behaviour.shell("svc wifi $arg")
        Behaviour.shell("svc data $arg")
    }

    @Before
    fun setUp() {
        // A previous aborted run may have left the radios off.
        setNetwork(true)
        SystemClock.sleep(1_000)

        // Fresh test users server-side (drops their photos too). Backend
        // down → skip, per the class contract.
        val code = Behaviour.post("http://10.0.2.2:8055/api/debug/recreate-test-users")
        assumeTrue("dev backend not reachable from the emulator (got $code)", code == 200)

        // The drain uploads EVERYTHING pending, oldest first — leftovers
        // from the backend-free tests would put this test's photo at the
        // back of a long queue. Their rows are test artifacts; drop them
        // (files stay on disk).
        val dao = Behaviour.photoDao()
        (dao.getPendingUploads() + dao.getPhotosByUploadStatus("failed"))
            .forEach { dao.deletePhoto(it.id) }

        gps.install()
        GlobalContext.get().get<UploadSettingsRepository>().update {
            it.copy(
                license = it.license ?: ALLOWED_LICENSES.first(),
                autoUploadEnabled = true,
                // The reconnected network's metered classification is not
                // ours to assert — same reasoning as the Appium spec.
                wifiOnly = false,
            )
        }
    }

    @After
    fun tearDown() {
        try {
            setNetwork(true)
        } catch (_: Exception) {
            // best-effort — never leave the emulator offline for later specs
        }
        GlobalContext.get().get<UploadSettingsRepository>().update {
            it.copy(autoUploadEnabled = false)
        }
        try {
            runBlocking { GlobalContext.get().get<SessionManager>().logout() }
        } catch (_: Exception) {
            // the suite converges to logged-out when it can
        }
        gps.remove()
    }

    @Test
    fun queuesAnOfflineCaptureAndDrainsItOnReconnect() {
        compose.loginThroughTheUi()

        setNetwork(false)
        SystemClock.sleep(2_000)

        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()
        val photo = compose.captureOnePhoto()
        assertEquals("pending", photo.uploadStatus)

        // Parked, not failing: the CONNECTED constraint must hold the work
        // back entirely while offline — no attempts, no failure states.
        SystemClock.sleep(8_000)
        val dao = Behaviour.photoDao()
        val whileOffline = dao.getPhotoById(photo.id)!!
        assertEquals(
            "the drain must stay parked offline (got ${whileOffline.uploadStatus})",
            "pending",
            whileOffline.uploadStatus,
        )
        assertNull(whileOffline.serverPhotoId)

        setNetwork(true)

        // WorkManager's connectivity callback releases the queued drain;
        // generous deadline for the capped emulator.
        val deadline = SystemClock.elapsedRealtime() + 120_000
        var drained = dao.getPhotoById(photo.id)!!
        while (SystemClock.elapsedRealtime() < deadline &&
            drained.serverPhotoId == null &&
            drained.uploadStatus !in listOf("processing", "completed")
        ) {
            SystemClock.sleep(3_000)
            drained = dao.getPhotoById(photo.id)!!
        }

        Log.i(
            "UploadQueueOffline",
            "drained: status=${drained.uploadStatus} serverPhotoId=${drained.serverPhotoId}",
        )
        assertTrue(
            "queued capture did not reach the server after reconnect " +
                "(status=${drained.uploadStatus}, error=${drained.uploadError})",
            drained.serverPhotoId != null ||
                drained.uploadStatus in listOf("processing", "completed"),
        )
    }
}
