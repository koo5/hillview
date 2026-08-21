package cz.hillview.map

import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

/**
 * Hunter mode and the filter override — which photos COUNT, as opposed to
 * where you are and which way you face (MapStateHolder).
 *
 * They lived as Compose state inside the map screen, which was fine while the
 * map was their only reader. It is not: hunter mode off collapses the
 * viewer's navigable ring to featured photos (see
 * docs/tauri-viewer-ui-contract.md), so the same two flags decide what the
 * map greys out AND what you can turn to. Two screens reading one fact means
 * it belongs outside both of them, for the same reason bearing does.
 *
 * Deliberately NOT folded into MapStateHolder: that funnel exists to enforce
 * the election and tracking rules on spatial/bearing writes, and this state
 * has neither. It does need the settings repository, which MapStateHolder
 * knows nothing about.
 */
class MapFilterState(
    private val settings: MapSettingsRepository,
    scope: CoroutineScope,
) {
    /**
     * Per-session override of the persisted preference; null means "follow
     * the preference". Kept separate from the preference itself so that
     * toggling the mode in the UI can clear the override and write the pref,
     * exactly as the map screen did inline.
     */
    private val _hunterOverride = MutableStateFlow<Boolean?>(null)

    /** The effective mode: the session override, else the saved preference. */
    val hunterMode: StateFlow<Boolean> =
        combine(_hunterOverride, settings.settings) { override, saved ->
            override ?: saved.hunterModePref
        }.stateIn(
            scope,
            SharingStarted.Eagerly,
            _hunterOverride.value ?: settings.settings.value.hunterModePref,
        )

    /** Session-only, exactly as in the Svelte app: never persisted. */
    private val _overrideFilters = MutableStateFlow(false)
    val overrideFilters: StateFlow<Boolean> = _overrideFilters

    /**
     * Tapping a greyed-out photo un-greys the set — the original's
     * overrideFilters flip, which reaches for hunter mode rather than the
     * filter override because that is what the Svelte app does.
     */
    fun revealHiddenPhotos() {
        if (!hunterMode.value) _hunterOverride.value = true
    }

    /** The toggle: drop any override and flip the saved preference. */
    fun toggleHunterMode() {
        val next = !hunterMode.value
        _hunterOverride.value = null
        settings.update { it.copy(hunterModePref = next) }
    }

    fun toggleOverrideFilters() {
        _overrideFilters.value = !_overrideFilters.value
    }
}
