package cz.hillview

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.assertTextEquals
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import cz.hillview.settings.LICENSE_INFO
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.UploadSettingsRepository
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.koin.core.context.GlobalContext

/** Each choice explains itself without silently accepting the grant. */
@RunWith(AndroidJUnit4::class)
class LicenseChoicesBehaviourTest {
    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()
    private val settings: UploadSettingsRepository get() = GlobalContext.get().get()
    private lateinit var original: UploadSettings

    @Before
    fun prepare() {
        original = settings.settings.value
        settings.update { it.copy(license = null, autoUploadEnabled = false) }
    }

    @After
    fun restore() { settings.update { original } }

    @Test
    fun eachHelpLinkOpensItsOwnGrantAndLeavesConsentUnchanged() {
        compose.openMenu()
        compose.onNodeWithTag("settings-menu-link").performClick()
        // Check reading both unaccepted and accepted options.
        for (accepted in listOf<String?>(null, "panoramax_in")) {
            settings.update { it.copy(license = accepted) }
            LICENSE_INFO.forEach { license ->
                compose.onNodeWithTag("settings-license-help-${license.id}")
                    .performScrollTo().performTouchInput { click() }
                compose.onNodeWithTag("license-info-${license.id}").assertIsDisplayed()
                compose.onNodeWithTag("license-info-title").assertTextEquals(license.label)
                assertEquals(accepted, settings.settings.value.license)
                compose.onNodeWithTag("license-info-back").performTouchInput { click() }
                assertEquals(accepted, settings.settings.value.license)
            }
        }
        settings.update { it.copy(license = null) }
        assertNull(settings.settings.value.license)
        LICENSE_INFO.forEach { license ->
            compose.onNodeWithTag("settings-license-${license.id}")
                .performScrollTo().performTouchInput { click() }.assertIsSelected()
            assertEquals(license.id, settings.settings.value.license)
        }
    }
}
