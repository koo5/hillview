package cz.hillview.settings

import kotlinx.coroutines.flow.StateFlow

data class CompassSettings(
    /**
     * Negate the heading when the device is face-down in landscape. A
     * device-specific magnetometer/rotation-vector quirk (found on an Armor
     * 22); off by default. The shared-kt EnhancedSensorService reads this
     * straight from its own prefs file — this repository only toggles it.
     */
    val landscapeWorkaround: Boolean = false,
)

interface CompassSettingsRepository {
    val settings: StateFlow<CompassSettings>
    fun update(transform: (CompassSettings) -> CompassSettings)
}
