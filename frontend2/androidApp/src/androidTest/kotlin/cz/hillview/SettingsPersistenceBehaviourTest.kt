package cz.hillview

import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import cz.hillview.settings.ALLOWED_LICENSES
import cz.hillview.settings.CompassSettingsRepository
import cz.hillview.settings.PrefsUploadSettingsRepository
import cz.hillview.settings.UploadSettingsRepository
import cz.hillview.settings.defaultUploadSettings
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/**
 * Settings persistence — the port of settings-persistence.test.ts. The
 * Tauri bug it guards against (a partial set_settings params object
 * silently defaulting missing keys to false) has a structural fix here —
 * `update(transform)` always persists the complete settings object — but
 * the invariants stay worth asserting from the UI: what a control writes,
 * what a restart reads back, and that touching one setting never stomps
 * another (including across pref files: upload vs compass).
 *
 * Scope-down, stated honestly: instrumentation dies with the process, so
 * the Appium spec's real kill+relaunch becomes (a) the raw
 * SharedPreferences contents — exactly what a dead process leaves behind —
 * (b) a fresh repository construction, which IS the startup load path, and
 * (c) activity recreation with the UI re-read from the repositories.
 */
@RunWith(AndroidJUnit4::class)
class SettingsPersistenceBehaviourTest {

    @get:Rule(order = 0)
    val permissions: GrantPermissionRule = GrantPermissionRule.grant(
        // Turning auto-upload on requests notification permission; granted
        // up front so no system dialog blocks the semantics tree.
        android.Manifest.permission.POST_NOTIFICATIONS,
    )

    @get:Rule(order = 1)
    val compose = createAndroidComposeRule<MainActivity>()

    private val uploadPrefs
        get() = Behaviour.context.getSharedPreferences("hillview_upload_prefs", 0)
    private val compassPrefs
        get() = Behaviour.context.getSharedPreferences("hillview_compass_prefs", 0)

    @After
    fun restorePrivacyDefaults() {
        GlobalContext.get().get<UploadSettingsRepository>().update {
            it.copy(autoUploadEnabled = false, wifiOnly = false)
        }
        // The compass pref is shared with the Tauri app's sensor stack on
        // this device — leave it as found-by-default.
        GlobalContext.get().get<CompassSettingsRepository>().update {
            it.copy(landscapeWorkaround = false)
        }
    }

    private fun openSettings() {
        compose.openMenu()
        compose.onNodeWithTag("settings-menu-link").performClick()
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("settings-auto-upload")
                .fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun goHome() {
        compose.activityRule.scenario.onActivity {
            it.onBackPressedDispatcher.onBackPressed()
        }
        compose.waitUntil(10_000) {
            compose.onAllNodesWithTag("hamburger-menu")
                .fetchSemanticsNodes().isNotEmpty()
        }
    }

    private fun recreateAndReopenSettings() {
        compose.activityRule.scenario.recreate()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithTag("hamburger-menu")
                .fetchSemanticsNodes().isNotEmpty()
        }
        openSettings()
    }

    private fun pickLicense(license: String) {
        compose.onNodeWithTag("settings-license-$license")
            .performScrollTo()
            .performClick()
        compose.onNodeWithTag("settings-license-$license").assertIsSelected()
    }

    @Test
    fun uploadSettingsSurviveRestart() {
        openSettings()
        pickLicense(ALLOWED_LICENSES.first())
        compose.setSwitch("settings-auto-upload", true)
        compose.setSwitch("settings-wifi-only", true)
        goHome()

        // (a) What the dead process would leave on disk.
        assertTrue(uploadPrefs.getBoolean("auto_upload_enabled", false))
        assertTrue(uploadPrefs.getBoolean("wifi_only", false))
        assertEquals(
            ALLOWED_LICENSES.first(),
            uploadPrefs.getString("auto_upload_license", null),
        )

        // (b) The startup load path: a fresh repository over the same prefs.
        // (Its constructor re-persists what it loads, so this also proves
        // construction is read-only in effect.)
        val fresh = PrefsUploadSettingsRepository(
            Behaviour.context,
            defaultUploadSettings("http://unused.invalid/api"),
        ).settings.value
        assertTrue(fresh.autoUploadEnabled)
        assertTrue(fresh.wifiOnly)
        assertEquals(ALLOWED_LICENSES.first(), fresh.license)

        // (c) The UI after activity death reads it all back.
        recreateAndReopenSettings()
        compose.onNodeWithTag("settings-auto-upload").performScrollTo().assertIsOn()
        compose.onNodeWithTag("settings-wifi-only").performScrollTo().assertIsOn()
        compose.onNodeWithTag("settings-license-${ALLOWED_LICENSES.first()}")
            .performScrollTo().assertIsSelected()
    }

    /**
     * The canonical merge test: one control, one key. Before the Tauri fix,
     * flipping wifi_only stomped auto_upload_enabled and the prompt flag.
     */
    @Test
    fun wifiOnlyToggleDoesNotStompTheRest() {
        openSettings()
        pickLicense(ALLOWED_LICENSES.first())
        compose.setSwitch("settings-auto-upload", true)
        compose.setSwitch("settings-wifi-only", true)
        goHome()
        val licenseBefore = uploadPrefs.getString("auto_upload_license", null)
        val promptBefore = uploadPrefs.getBoolean("auto_upload_prompt_enabled", true)
        val storageBefore = uploadPrefs.getString("preferred_storage", null)

        openSettings()
        compose.setSwitch("settings-wifi-only", false)
        goHome()

        assertTrue(!uploadPrefs.getBoolean("wifi_only", true))
        assertTrue(uploadPrefs.getBoolean("auto_upload_enabled", false))
        assertEquals(licenseBefore, uploadPrefs.getString("auto_upload_license", null))
        assertEquals(promptBefore, uploadPrefs.getBoolean("auto_upload_prompt_enabled", !promptBefore))
        assertEquals(storageBefore, uploadPrefs.getString("preferred_storage", null))
    }

    /**
     * Cross-file independence: the compass workaround lives in
     * hillview_compass_prefs (read directly by shared-kt's sensor service),
     * upload settings in hillview_upload_prefs. Changing one must not drag
     * the other along — the Appium spec's cross-category merge case.
     */
    @Test
    fun compassSettingPersistsIndependentlyOfUploadChanges() {
        openSettings()
        compose.setSwitch("settings-landscape-workaround", true)
        goHome()
        assertTrue(compassPrefs.getBoolean("landscape_armor22_workaround", false))

        // Touch an upload setting…
        openSettings()
        pickLicense(ALLOWED_LICENSES.last())
        goHome()

        // …and the compass flag neither moved nor got dragged into the
        // upload file.
        assertTrue(compassPrefs.getBoolean("landscape_armor22_workaround", false))
        assertEquals(
            ALLOWED_LICENSES.last(),
            uploadPrefs.getString("auto_upload_license", null),
        )

        recreateAndReopenSettings()
        compose.onNodeWithTag("settings-landscape-workaround")
            .performScrollTo().assertIsOn()
    }
}
