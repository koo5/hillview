package cz.hillview

import android.content.Context
import android.net.Uri
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.capture.PhotoTableDump
import cz.hillview.plugin.AuthenticationManager
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Capture consent must survive both the queued row and its public CSV export. */
@RunWith(AndroidJUnit4::class)
class PanoramaxCaptureBehaviourTest {
    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        android.Manifest.permission.ACCESS_FINE_LOCATION,
        android.Manifest.permission.ACCESS_COARSE_LOCATION,
        android.Manifest.permission.CAMERA,
    )
    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()
    private val gps = MockGps()
    private val settings: UploadSettingsRepository get() = GlobalContext.get().get()
    private lateinit var original: UploadSettings

    @Before
    fun prepare() {
        original = settings.settings.value
        settings.update { it.copy(license = "full1", shareToPanoramax = false,
            autoUploadEnabled = false, autoUploadPromptEnabled = false) }
        gps.install()
    }

    @After
    fun restore() {
        gps.remove()
        settings.update { original }
    }

    @Test
    fun sharedCaptureUploadsAndCardWithdrawalReachesTheBackend() {
        compose.loginThroughTheUi()
        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()
        compose.onNodeWithTag("capture-panoramax-toggle").performClick().assertIsSelected()
        val photo = compose.captureOnePhoto()
        val dao = Behaviour.photoDao()
        PhotoUploadManager(Behaviour.context).startManualUpload(photo.id)
        compose.waitUntil(120_000) { dao.getPhotoById(photo.id)?.serverPhotoId != null }
        val serverId = dao.getPhotoById(photo.id)!!.serverPhotoId!!
        val apiUrl = settings.settings.value.serverUrl.trimEnd('/')
        fun serverPhoto(): JSONObject {
            val connection = URL("$apiUrl/photos/public/hillview-$serverId").openConnection() as HttpURLConnection
            connection.connectTimeout = 5_000
            connection.readTimeout = 5_000
            val token = AuthenticationManager(Behaviour.context).getTokenInfo().first!!
            connection.setRequestProperty("Authorization", "Bearer $token")
            return try {
                assertEquals(200, connection.responseCode)
                connection.inputStream.bufferedReader().use { JSONObject(it.readText()) }
            } finally { connection.disconnect() }
        }
        assertTrue(serverPhoto().getBoolean("panoramax_share"))
        assertEquals("full1", serverPhoto().getString("license_granted"))
        assertEquals("panoramax", serverPhoto().getString("license"))
        // Automatic file uploads remain OFF; an explicit metadata wish must still drain.
        assertFalse(settings.settings.value.autoUploadEnabled)
        compose.openMenu()
        compose.onNodeWithTag("menu-device-photos").performClick()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("photo-panoramax-share-button").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onAllNodesWithTag("photo-panoramax-share-button")[0]
            .performScrollTo().assertTextEquals("Panoramax: on").performClick()
        compose.waitUntil(60_000) { !serverPhoto().getBoolean("panoramax_share") }
        assertFalse(dao.getPhotoById(photo.id)!!.panoramaxShare)
        assertEquals("arr", serverPhoto().getString("license"))
    }

    @Test
    fun toggleIsSnapshottedAndExportedWithThePhoto() {
        compose.openCaptureAndAwaitCamera()
        compose.ensureCaptureReady()
        compose.onNodeWithTag("capture-panoramax-toggle").performClick().assertIsSelected()
        val photo = compose.captureOnePhoto()
        assertTrue(photo.panoramaxShare)
        compose.onNodeWithTag("capture-panoramax-toggle").performClick()
        assertTrue(Behaviour.photoDao().getPhotoById(photo.id)!!.panoramaxShare)

        runBlocking { PhotoTableDump.dumpNowForResult(Behaviour.context) }
        val uris = Behaviour.context.getSharedPreferences("hillview_photo_dump", Context.MODE_PRIVATE)
            .getString("last_shard_uris", "").orEmpty().split(',').filter { it.isNotEmpty() }
        assertTrue("the dump must be published through MediaStore", uris.isNotEmpty())
        val rows = uris.flatMap { uri ->
            val text = Behaviour.context.contentResolver.openInputStream(Uri.parse(uri))!!
                .bufferedReader().use { it.readText() }
            val file = java.io.File.createTempFile("panoramax-dump", ".csv", Behaviour.context.cacheDir)
            try {
                // The first line is the export checkpoint; the next is the CSV header.
                file.writeText(text.substringAfter('\n'))
                Behaviour.geoDumpRows(file)
            } finally { file.delete() }
        }
        val exported = rows.last { it["id"] == photo.id }
        assertEquals("1", exported["panoramaxShare"])
    }
}
