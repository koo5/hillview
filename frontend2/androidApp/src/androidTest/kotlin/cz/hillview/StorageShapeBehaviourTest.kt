package cz.hillview

import android.net.Uri
import android.os.Environment
import android.util.Log
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.settings.StorageMode
import org.junit.After
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Storage-shape assertions — the port of storage-method-pref.test.ts, and
 * the same honesty contract: each preference must produce a photo saved in
 * ONE of the recognized locations (the fallback chain working end-to-end),
 * but which method actually wins is API-level-dependent by design, so it is
 * logged as a matrix cell rather than asserted.
 *
 * Two things this port adds over the original: the locator is read straight
 * from the shared-kt Room DB (no plugin round-trip), and the saved bytes are
 * proven readable — a DB row pointing at a failed write cannot pass.
 */
@RunWith(AndroidJUnit4::class)
class StorageShapeBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val gps = MockGps()

    @Before
    fun maskTheRealGps() {
        // No fix → the map-position lift is always offered → the capture path
        // is identical and deterministic across the three cases.
        gps.install()
    }

    @After
    fun unmaskTheRealGps() {
        gps.remove()
    }

    /** Both folder spellings are valid — hide-from-gallery prefixes a dot. */
    private fun classify(locator: String): String? {
        val publicDcim = Environment
            .getExternalStoragePublicDirectory(Environment.DIRECTORY_DCIM).absolutePath
        val privatePictures = Behaviour.context
            .getExternalFilesDir(Environment.DIRECTORY_PICTURES)!!.absolutePath
        return when {
            locator.startsWith("content://") -> StorageMode.MediaStore.key
            locator.startsWith("$publicDcim/Hillview/") ||
                locator.startsWith("$publicDcim/.Hillview/") -> StorageMode.PublicFolder.key
            locator.startsWith("$privatePictures/Hillview/") ||
                locator.startsWith("$privatePictures/.Hillview/") -> StorageMode.PrivateFolder.key
            else -> null
        }
    }

    private fun locatorHasBytes(locator: String): Boolean =
        if (locator.startsWith("content://")) {
            Behaviour.context.contentResolver.openInputStream(Uri.parse(locator))
                ?.use { it.read() >= 0 } ?: false
        } else {
            File(locator).length() > 0
        }

    private fun runCase(mode: StorageMode) {
        // The preference is chosen through the real settings radio, as the
        // Appium spec drives it.
        compose.onNodeWithTag("home-settings-button").performClick()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("settings-storage-${mode.key}")
                .fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithTag("settings-storage-${mode.key}")
            .performScrollTo()
            .performClick()
        compose.activityRule.scenario.onActivity {
            it.onBackPressedDispatcher.onBackPressed()
        }
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("home-capture-button")
                .fetchSemanticsNodes().isNotEmpty()
        }

        compose.openCaptureAndAwaitCamera()
        compose.liftGateToMapPosition()
        val photo = compose.captureOnePhoto()

        val actual = classify(photo.path)
        // The matrix cell: which method actually won for this preference on
        // this API level. Runs against several images build the reference.
        Log.i(
            "StorageShape",
            "preference=${mode.key} → landed via ${actual ?: "UNRECOGNIZED"} (${photo.path})",
        )
        assertNotNull("unrecognized save location: ${photo.path}", actual)
        assertTrue("saved photo has no readable bytes: ${photo.path}", locatorHasBytes(photo.path))
    }

    @Test
    fun publicFolderPreferenceSavesSomewhereValid() = runCase(StorageMode.PublicFolder)

    @Test
    fun privateFolderPreferenceSavesSomewhereValid() = runCase(StorageMode.PrivateFolder)

    @Test
    fun mediaStorePreferenceSavesSomewhereValid() = runCase(StorageMode.MediaStore)
}
