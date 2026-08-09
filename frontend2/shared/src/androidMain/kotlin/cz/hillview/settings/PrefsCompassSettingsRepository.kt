package cz.hillview.settings

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Writes the exact pref the shared-kt EnhancedSensorService reads on every
 * rotation-vector event: file "hillview_compass_prefs", key
 * "landscape_armor22_workaround" (its own default is false). Same contract
 * the Tauri app's CompassSettings.svelte drives, so a device tuned in one
 * app behaves the same in the other.
 */
class PrefsCompassSettingsRepository(context: Context) : CompassSettingsRepository {
    private val prefs =
        context.getSharedPreferences("hillview_compass_prefs", Context.MODE_PRIVATE)

    private val _settings = MutableStateFlow(
        CompassSettings(
            landscapeWorkaround = prefs.getBoolean("landscape_armor22_workaround", false),
        )
    )
    override val settings: StateFlow<CompassSettings> = _settings.asStateFlow()

    override fun update(transform: (CompassSettings) -> CompassSettings) {
        val next = transform(_settings.value)
        prefs.edit()
            .putBoolean("landscape_armor22_workaround", next.landscapeWorkaround)
            .apply()
        _settings.value = next
    }
}
