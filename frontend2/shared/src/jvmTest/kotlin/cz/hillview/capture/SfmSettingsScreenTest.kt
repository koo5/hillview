package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.settings.MapSettings
import cz.hillview.settings.MapSettingsRepository
import cz.hillview.settings.overlapSpacing
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The SfM run's page (user, 2026-11-05: "lets make it all opt-in and
 * configurable"): off by default with nothing else on show, and every
 * trigger its own switch once it is on.
 */
@OptIn(ExperimentalTestApi::class)
class SfmSettingsScreenTest {

    private class FakeSettings(initial: MapSettings = MapSettings()) : MapSettingsRepository {
        private val _settings = MutableStateFlow(initial)
        override val settings: StateFlow<MapSettings> = _settings
        override fun update(transform: (MapSettings) -> MapSettings) {
            _settings.value = transform(_settings.value)
        }
    }

    @Test
    fun offByDefaultAndNothingElseShows() = runComposeUiTest {
        val repo = FakeSettings()
        setContent { SfmSettingsScreen(onBack = {}, repository = repo) }
        onNodeWithTag("sfm-enabled").assertIsOff()
        onNodeWithTag("sfm-distance-on").assertDoesNotExist()
        onNodeWithTag("sfm-min-gap-slider").assertDoesNotExist()
    }

    @Test
    fun optingInShowsEachTriggerAndSwitchingOneOffHidesItsValue() = runComposeUiTest {
        val repo = FakeSettings()
        setContent { SfmSettingsScreen(onBack = {}, repository = repo) }
        onNodeWithTag("sfm-enabled").performClick()
        assertTrue(repo.settings.value.sfmRunEnabled)
        for (tag in listOf("sfm-metres-slider", "sfm-turn-slider", "sfm-heartbeat-slider", "sfm-min-gap-slider")) {
            onNodeWithTag(tag).assertExists()
        }
        onNodeWithTag("sfm-turn-on").performClick()
        assertFalse(repo.settings.value.sfmTurnOn)
        onNodeWithTag("sfm-turn-slider").assertDoesNotExist()
        assertEquals(null, repo.settings.value.overlapSpacingOrNull()?.turnDeg)
    }

    @Test
    fun withNothingPacingTheRunItSaysSo() = runComposeUiTest {
        val repo = FakeSettings(
            MapSettings(sfmRunEnabled = true, sfmDistanceOn = false, sfmTurnOn = false, sfmHeartbeatOn = false),
        )
        setContent { SfmSettingsScreen(onBack = {}, repository = repo) }
        onNodeWithTag("sfm-nothing-paces").assertExists()
    }

    @Test
    fun metresReadWithoutATrailingZero() {
        assertEquals("1.5 m", formatMetres(1.5f))
        assertEquals("2 m", formatMetres(2f))
        assertEquals("0.3 m", formatMetres(0.3f))
    }

    private fun MapSettings.overlapSpacingOrNull() = overlapSpacing()
}
