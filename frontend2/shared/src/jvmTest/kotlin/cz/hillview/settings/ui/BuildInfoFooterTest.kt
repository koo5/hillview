package cz.hillview.settings.ui

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.v2.runComposeUiTest
import kotlin.test.Test

@OptIn(ExperimentalTestApi::class)
class BuildInfoFooterTest {

    @Test
    fun settingsShowsTheBuildIdentity() = runComposeUiTest {
        setContent { BuildInfoFooter(label = "0.1.0 · a0bc3a1c · 2026-08-27T02:58:11+02:00") }
        onNodeWithTag("settings-build-info")
            .assertIsDisplayed()
            .assertTextContains("a0bc3a1c", substring = true)
    }
}
