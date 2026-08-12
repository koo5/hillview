package cz.hillview.geo

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import androidx.core.content.ContextCompat
import cz.hillview.plugin.EnhancedSensorService
import cz.hillview.plugin.GeoTrackingManager
import cz.hillview.plugin.OrientationSensorData
import cz.hillview.plugin.PreciseLocationData
import cz.hillview.plugin.PreciseLocationService
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow

private const val TAG = "GeoEngine"

/**
 * What to run the hardware at. The engine is TOLD this; it never decides —
 * same rule as its flows, which carry samples and no policy.
 *
 * The values live at the call site that starts the engine for an activity
 * (see MainScreen), not in an enum here, so a user-facing control — the GPS
 * interval slider, the eco sub-flags — is a value flowing through rather
 * than a new mechanism needing the path re-plumbed.
 */
data class GeoConfig(
    val sensors: Boolean,
    /** SensorManager sampling period hint, microseconds. */
    val sensorDelayUs: Int,
    /** Fused-location interval, milliseconds. */
    val locationIntervalMs: Long,
) {
    companion object {
        val Off = GeoConfig(sensors = false, sensorDelayUs = 0, locationIntervalMs = 0)
    }
}

/**
 * The ONE owner of position and heading hardware — the CMP analog of the
 * Tauri plugin's hardware half (`ExamplePlugin`), which holds exactly one
 * `EnhancedSensorService` and one `PreciseLocationService` and fans each
 * sample out from a single callback.
 *
 * Before this existed, frontend2 had THREE of each (map, capture, external),
 * each writing the tracking tables independently, and only one of them also
 * feeding the value the app stamps photos with — which is how the external
 * pane ended up displaying a compass reading that was not the app's. Full
 * reasoning: docs/frontend2-geo-engine-design.md.
 *
 * Every sample does here exactly what the plugin's callback does:
 *  - the tracking TABLE at full rate (the authoritative time-indexed record
 *    that retroactive pairing, the CSVs and the stamp refiner read),
 *  - the declination feed into the sensor stack,
 *  - the car-mode Kalman derivation,
 *  - publication as flows, which every pane observes instead of opening its
 *    own hardware.
 *
 * THREADING: callbacks land on this engine's own [HandlerThread], not the
 * main looper. Both shared-kt services default to the main looper — which is
 * what the Tauri app still uses, and gets away with because its map draws in
 * the WebView's renderer process. A CMP map draws on the main thread, so a
 * heavy marker pass would otherwise delay a fix and therefore delay the value
 * a capture stamps.
 */
class GeoEngine private constructor(private val context: Context) {

    companion object {
        @Volatile
        private var INSTANCE: GeoEngine? = null

        fun get(context: Context): GeoEngine =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: GeoEngine(context.applicationContext).also { INSTANCE = it }
            }
    }

    // Two handlers, deliberately. SAMPLES are delivered on the geo thread —
    // that is the whole point, keeping the hot path off the main looper. But
    // CONFIGURATION runs on the main thread, because starting the sensor
    // stack registers a lifecycle observer and androidx enforces main there
    // ("Method addObserver must be called on the main thread" — caught on a
    // device the first time this ran). Config changes are rare (an activity
    // switch); samples are not.
    private val thread = HandlerThread("hillview-geo").apply { start() }
    private val handler = Handler(thread.looper)
    private val mainHandler = Handler(android.os.Looper.getMainLooper())

    private val geoTracking by lazy { GeoTrackingManager.get(context) }

    private var sensorService: EnhancedSensorService? = null
    private var locationService: PreciseLocationService? = null
    private var active: GeoConfig = GeoConfig.Off

    /** Latest orientation sample; null until the sensors produce one. */
    private val _orientation = MutableStateFlow<OrientationSensorData?>(null)
    val orientation: StateFlow<OrientationSensorData?> = _orientation.asStateFlow()

    /**
     * Latest fix, as the platform [Location] — deliberately not a lat/lng
     * pair: the capture stamp's `locationAgeMs` is computed from
     * `elapsedRealtimeNanos`, which only survives if the object does.
     */
    private val _location = MutableStateFlow<Location?>(null)
    val location: StateFlow<Location?> = _location.asStateFlow()

    /** The composed car-mode heading (Kalman + mount offset), per fix. */
    private val _carBearing = MutableSharedFlow<Double>(replay = 1, extraBufferCapacity = 8)
    val carBearing: SharedFlow<Double> = _carBearing.asSharedFlow()

    /** True while the fix stream is meant to be running (permission-gated). */
    private val _locationActive = MutableStateFlow(false)
    val locationActive: StateFlow<Boolean> = _locationActive.asStateFlow()

    /**
     * Apply a configuration. Idempotent: the same config twice is a no-op, so
     * a recomposing caller can hand it over freely.
     */
    fun configure(config: GeoConfig) {
        mainHandler.post { applyConfig(config) }
    }

    /** Car mode's heading filter is stateful — the map resets it on entry. */
    fun resetCarHeadingFilter() {
        handler.post { geoTracking.resetHeadingFilter() }
    }

    private fun applyConfig(config: GeoConfig) {
        if (config == active) return
        Log.i(TAG, "configure $active -> $config")
        cz.hillview.plugin.EventLog.record(
            "geo",
            "engine -> " + if (!config.sensors && config.locationIntervalMs == 0L) "off" else
                "sensors ${config.sensorDelayUs / 1000}ms, fixes ${config.locationIntervalMs}ms",
        )

        // Sensors.
        if (config.sensors && !active.sensors) {
            startSensors()
        } else if (!config.sensors && active.sensors) {
            stopSensors()
        } else if (config.sensors && config.sensorDelayUs != active.sensorDelayUs) {
            // The rate is fixed at registration, so a change is a restart.
            stopSensors()
            startSensors()
        }

        // Location.
        val wantLocation = config.locationIntervalMs > 0
        val hadLocation = active.locationIntervalMs > 0
        if (wantLocation && (!hadLocation || config.locationIntervalMs != active.locationIntervalMs)) {
            stopLocation()
            startLocation()
        } else if (!wantLocation && hadLocation) {
            stopLocation()
        }

        active = config
    }

    private fun startSensors() {
        if (sensorService != null) return
        sensorService = EnhancedSensorService(
            context = context,
            callbackHandler = handler,
        ) { data ->
            // One sample, fanned out — the plugin's shape exactly.
            geoTracking.storeOrientationSensorData(data)
            _orientation.value = data
        }.also { it.startSensor() }
    }

    private fun stopSensors() {
        sensorService?.let {
            try {
                it.stopSensor()
            } catch (e: Exception) {
                Log.w(TAG, "sensor stop failed", e)
            }
        }
        sensorService = null
    }

    private fun startLocation() {
        if (locationService != null) return
        if (!hasLocationPermission()) {
            Log.w(TAG, "location requested without permission — staying off")
            return
        }
        locationService = PreciseLocationService(
            context = context,
            onLocationUpdate = { data -> onFix(data) },
            onLocationStopped = { _locationActive.value = false },
            callbackLooper = thread.looper,
        ).also {
            it.startLocationUpdates()
            _locationActive.value = true
        }
    }

    private fun onFix(data: PreciseLocationData) {
        // Declination, so true heading stays true as the user travels.
        sensorService?.updateLocation(data.latitude, data.longitude)
        geoTracking.storeLocationPreciseLocationData(data)
        // Car mode's heading, derived HERE rather than in the map component:
        // it is a property of the fix stream, not of a pane being composed.
        // Rows are written by the filter against the fix's own timestamp.
        geoTracking.feedLocationForHeadingFilter(data)?.let { _carBearing.tryEmit(it) }
        _location.value = data.toLocation()
    }

    private fun stopLocation() {
        locationService?.let {
            try {
                it.stopLocationUpdates()
            } catch (e: Exception) {
                Log.w(TAG, "location stop failed", e)
            }
        }
        locationService = null
        _locationActive.value = false
    }

    fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
}

/**
 * The platform object the stamp needs. `elapsedRealtimeNanos` is the point:
 * fix age at the shutter is measured against the monotonic clock, and a
 * lat/lng pair would silently lose it.
 */
private fun PreciseLocationData.toLocation(): Location =
    Location(provider ?: "fused").also {
        it.latitude = latitude
        it.longitude = longitude
        it.time = timestamp
        it.elapsedRealtimeNanos = elapsedRealtimeNanos
        it.accuracy = accuracy
        altitude?.let { alt -> it.altitude = alt }
        speed?.let { s -> it.speed = s }
        bearing?.let { b -> it.bearing = b }
    }
