package cz.hillview.external

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Whether the external-camera activity logs inertial samples CONTINUOUSLY.
 *
 * On by default, because that is what the mode is for: an external camera's
 * frames are not ours to bracket, so there is no shutter to build a window
 * around, and shutter-detection experiments need the undecimated stream. Off is
 * a storage decision, not a correctness one — the samples run at
 * `SENSOR_DELAY_FASTEST` on two sensors, which is roughly 100 MB of CSV an hour,
 * and a multi-hour drive deserves a switch.
 *
 * WHY A SINGLETON AND NOT A REPOSITORY. The config has TWO claimants that must
 * agree: the activity binding (a composable) and `ExternalCameraService` (a
 * foreground service). `GeoEngine.mergedConfig` resolves `imuContinuous` with
 * `any { it.imuContinuous }`, so if one claimant said false and the other true,
 * TRUE would win and the switch would appear to do nothing. Both read here, and
 * both see the same value the moment it changes — which a per-screen state
 * holder could not promise, and which a DI-injected repository would have to be
 * plumbed into a Service to match.
 *
 * Prefs-backed for the same reason `CompassSettings` is: the service can be
 * restarted by the system without the UI, and the answer has to survive that.
 * Same shape as `PrefsCompassSettingsRepository`, which the shared-kt sensor
 * service also reads straight from prefs rather than through the repository.
 */
object ExternalImuSettings {

    private const val PREFS = "hillview_external_prefs"
    private const val KEY_CONTINUOUS = "imu_continuous"

    /** On by default — see the class note for why. */
    const val DEFAULT_CONTINUOUS = true

    private val _continuous = MutableStateFlow(DEFAULT_CONTINUOUS)

    /**
     * The live value. Reflects the stored one after the first [load]; until then
     * it is the default, which is the safe direction — a claim made before prefs
     * were read records samples rather than silently dropping them.
     */
    val continuous: StateFlow<Boolean> = _continuous.asStateFlow()

    /** Read the stored value into [continuous]. Idempotent, cheap, safe to repeat. */
    fun load(context: Context): Boolean {
        val v = prefs(context).getBoolean(KEY_CONTINUOUS, DEFAULT_CONTINUOUS)
        _continuous.value = v
        return v
    }

    fun setContinuous(context: Context, value: Boolean) {
        prefs(context).edit().putBoolean(KEY_CONTINUOUS, value).apply()
        _continuous.value = value
    }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
