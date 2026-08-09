package cz.hillview.capture

import android.os.Build
import androidx.test.platform.app.InstrumentationRegistry
import cz.hillview.settings.StorageMode
import cz.hillview.settings.storageFacts
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.Test

/**
 * Where captures are saved. On a device because the answers depend on the
 * running Android version and on real directories — see
 * docs/tauri-map-ui-contract.md for the version rules.
 */
class PhotoStorageTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Test
    fun theChainStartsWithThePreferredTargetAndKeepsTheRest() {
        // The point of the chain is that a blocked target degrades instead of
        // losing the photo.
        StorageMode.entries.forEach { preferred ->
            val chain = PhotoStorage.chain(preferred)
            assertEquals(preferred, chain.first(), "preferred target must be tried first")
            assertEquals(StorageMode.entries.size, chain.size, "no target may be dropped")
            assertEquals(chain.toSet().size, chain.size, "no target may be tried twice")
        }
    }

    @Test
    fun hidingSwitchesToADotFolder() {
        assertEquals("Hillview", PhotoStorage.folderName(hideFromGallery = false))
        assertEquals(".Hillview", PhotoStorage.folderName(hideFromGallery = true))
    }

    @Test
    fun theFolderNamesMatchTheTauriApp() {
        // Same names on purpose: a user switching apps should find one set of
        // photos, not two.
        assertTrue(PhotoStorage.publicDir(false).absolutePath.endsWith("/DCIM/Hillview"))
        assertTrue(
            PhotoStorage.privateDir(context, false).absolutePath
                .contains("/Android/data/${context.packageName}/files/Pictures/Hillview"),
        )
    }

    @Test
    fun preparingATargetCreatesItsDirectory() {
        val prepared = PhotoStorage.outputOptions(
            context, StorageMode.PrivateFolder, "probe.jpg", hideFromGallery = false,
        )
        assertNotNull(prepared, "the app-private target is always available")
        val (_, file) = prepared
        assertNotNull(file)
        assertTrue(file.parentFile?.isDirectory == true, "the directory must exist before capture")
    }

    @Test
    fun mediaStoreSavesReportAUriRatherThanAFile() {
        val prepared = PhotoStorage.outputOptions(
            context, StorageMode.MediaStore, "probe.jpg", hideFromGallery = false,
        )
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        assertNotNull(prepared)
        assertEquals(null, prepared.second, "MediaStore has no File behind it — the locator is a content URI")
    }

    @Test
    fun thePlatformFactsMatchThisDevicesAndroidVersion() {
        val sdk = Build.VERSION.SDK_INT
        val private = storageFacts(StorageMode.PrivateFolder, hideFromGallery = false)
        assertFalse(private.inGallery, "app-private photos are never in the gallery")
        assertFalse(private.survivesUninstall)
        assertEquals(
            sdk < Build.VERSION_CODES.R,
            private.fileManagerReachable,
            "Android 11 closed Android/data to other apps",
        )

        val mediaStore = storageFacts(StorageMode.MediaStore, hideFromGallery = false)
        assertEquals(
            sdk >= Build.VERSION_CODES.Q,
            mediaStore.availableHere,
            "MediaStore's RELATIVE_PATH only exists from Android 10",
        )

        val public = storageFacts(StorageMode.PublicFolder, hideFromGallery = false)
        assertEquals(
            sdk >= Build.VERSION_CODES.R,
            public.availableHere,
            "a direct DCIM write needs Android 11, or a permission this app does not request",
        )
    }

    @Test
    fun hidingCannotWorkThroughMediaStore() {
        // Verified on API 36: the system rewrites ".Hillview" to "_.Hillview"
        // and indexes the photo anyway, so the UI must not promise hiding.
        val facts = storageFacts(StorageMode.MediaStore, hideFromGallery = true)
        assertTrue(facts.inGallery, "MediaStore entries stay visible even when hiding was asked for")
        assertTrue(facts.note.contains("hidden", ignoreCase = true), "and the UI must say so: ${facts.note}")
    }
}
