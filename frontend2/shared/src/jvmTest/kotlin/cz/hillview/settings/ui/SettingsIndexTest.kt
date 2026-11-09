package cz.hillview.settings.ui

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.settings.MapSettings
import cz.hillview.settings.ShutterSound
import cz.hillview.settings.SoundChannel
import cz.hillview.settings.StorageMode
import cz.hillview.settings.defaultUploadSettings
import kotlin.test.Test
import kotlin.test.assertEquals

@OptIn(ExperimentalTestApi::class)
class SettingsIndexTest {

    private val api = "https://hillview.cz/api"
    private val base = defaultUploadSettings(api)

    @Test
    fun everySectionIsListedAndOpensItself() = runComposeUiTest {
        val opened = mutableListOf<SettingsSection>()
        var backs = 0
        setContent {
            SettingsIndex(
                upload = base,
                map = MapSettings(),
                loggedIn = true,
                runtimeApiUrl = api,
                onBack = { backs++ },
                onOpenSection = { opened += it },
                buildInfo = {},
            )
        }
        SettingsSection.entries.forEach { section ->
            onNodeWithTag("settings-section-link-${section.key}").performClick()
        }
        assertEquals(SettingsSection.entries.toList(), opened.toList())
        onNodeWithTag("settings-screen-back").performClick()
        assertEquals(1, backs)
    }

    @Test
    fun summaryLinesSayWhatIsSet() = runComposeUiTest {
        setContent {
            SettingsIndex(
                upload = base.copy(license = null),
                map = MapSettings(),
                loggedIn = false,
                runtimeApiUrl = api,
                onBack = {},
                onOpenSection = {},
                buildInfo = {},
            )
        }
        onNodeWithTag("settings-section-summary-uploads", useUnmergedTree = true)
            .assertTextEquals("No licence picked — photos stay on this phone · not signed in")
        onNodeWithTag("settings-section-summary-servers", useUnmergedTree = true).assertTextEquals("hillview.cz")
    }

    @Test
    fun summaries() {
        val map = MapSettings()
        fun s(section: SettingsSection, upload: cz.hillview.settings.UploadSettings = base, m: MapSettings = map) =
            settingsSectionSummary(section, upload, m, loggedIn = true, runtimeApiUrl = api)

        val licensed = base.copy(license = "full1", autoUploadEnabled = true, wifiOnly = true)
        assertEquals("Auto-upload on Wi-Fi · Full rights to Hillview", s(SettingsSection.Uploads, licensed))
        assertEquals(
            "Auto-upload off · Full rights to Hillview",
            s(SettingsSection.Uploads, licensed.copy(autoUploadEnabled = false)),
        )

        assertEquals(
            "Silent · SfM run on",
            s(
                SettingsSection.Capture,
                base.copy(shutterSound = ShutterSound.Off, warnDegradedPosition = false),
                map.copy(sfmRunEnabled = true),
            ),
        )
        assertEquals(
            "Shutter: beep · Alarm volume · SfM run off",
            s(
                SettingsSection.Capture,
                base.copy(shutterSound = ShutterSound.Beep, captureSoundChannel = SoundChannel.Alarm),
                map.copy(sfmRunEnabled = false),
            ),
        )

        assertEquals(
            "App-private folder · hidden from the gallery · EXIF written",
            s(
                SettingsSection.Storage,
                base.copy(storage = StorageMode.PrivateFolder, hideFromGallery = true, writeExif = true),
            ),
        )

        // A changed URL is only live after a restart; the list says so.
        assertEquals(
            "hv.dev4.local — restart the app to apply",
            s(SettingsSection.Servers, base.copy(serverUrl = "https://hv.dev4.local/api")),
        )
    }
}
