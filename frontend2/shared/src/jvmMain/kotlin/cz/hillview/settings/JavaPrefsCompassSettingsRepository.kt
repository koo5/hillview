package cz.hillview.settings

import java.util.prefs.Preferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Desktop has no compass; the toggle persists so the screen behaves the same. */
class JavaPrefsCompassSettingsRepository : CompassSettingsRepository {
    private val node = Preferences.userRoot().node("cz/hillview/frontend2/compass_settings")

    private val _settings = MutableStateFlow(
        CompassSettings(landscapeWorkaround = node.getBoolean("landscape_workaround", false))
    )
    override val settings: StateFlow<CompassSettings> = _settings.asStateFlow()

    override fun update(transform: (CompassSettings) -> CompassSettings) {
        val next = transform(_settings.value)
        node.putBoolean("landscape_workaround", next.landscapeWorkaround)
        _settings.value = next
    }
}
