package cz.hillview.map

import cz.hillview.settings.MapSettings
import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Hunter mode and the filter override, now that two screens read them.
 * Behaviour is the map screen's, moved rather than redesigned.
 */
class MapFilterStateTest {

    private class FakeSettings(initial: MapSettings = MapSettings()) : MapSettingsRepository {
        private val _settings = MutableStateFlow(initial)
        override val settings: StateFlow<MapSettings> = _settings
        override fun update(transform: (MapSettings) -> MapSettings) {
            _settings.value = transform(_settings.value)
        }
    }

    private fun state(settings: FakeSettings = FakeSettings()) =
        MapFilterState(settings, CoroutineScope(Dispatchers.Unconfined))

    @Test
    fun hunterModeFollowsTheSavedPreference() {
        val settings = FakeSettings(MapSettings(hunterModePref = true))
        assertTrue(state(settings).hunterMode.value)
    }

    @Test
    fun togglingClearsTheOverrideAndWritesThePreference() {
        val settings = FakeSettings(MapSettings(hunterModePref = false))
        val filters = state(settings)

        filters.toggleHunterMode()

        assertTrue(filters.hunterMode.value)
        assertTrue(settings.settings.value.hunterModePref, "the toggle persists")
    }

    @Test
    fun revealingHiddenPhotosOverridesForThisSessionOnly() {
        // Tapping a greyed-out photo un-greys the set without changing what
        // the user chose to keep.
        val settings = FakeSettings(MapSettings(hunterModePref = false))
        val filters = state(settings)

        filters.revealHiddenPhotos()

        assertTrue(filters.hunterMode.value)
        assertFalse(settings.settings.value.hunterModePref, "the preference is untouched")
    }

    @Test
    fun revealingIsANoOpWhenNothingIsHidden() {
        val settings = FakeSettings(MapSettings(hunterModePref = true))
        val filters = state(settings)
        filters.revealHiddenPhotos()
        assertTrue(filters.hunterMode.value)
        assertTrue(settings.settings.value.hunterModePref)
    }

    @Test
    fun theFilterOverrideIsSessionOnly() {
        val settings = FakeSettings()
        val filters = state(settings)
        assertEquals(false, filters.overrideFilters.value)

        filters.toggleOverrideFilters()
        assertEquals(true, filters.overrideFilters.value)
        // Nothing about it is persisted, exactly as in the Svelte app.
        assertEquals(MapSettings(), settings.settings.value)
    }
}
