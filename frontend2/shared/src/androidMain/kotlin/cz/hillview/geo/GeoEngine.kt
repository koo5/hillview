package cz.hillview.geo

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import cz.hillview.capture.CaptureStatsLog
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

// Liveness watchdog. A REGISTERED sensor listener in the foreground delivers
// raw events at tens of Hz without pause, so seconds of silence mean the
// registration is dead (seen after unbackgrounding: compass and fix both
// frozen, everything downstream healthy) and the only cure is a fresh one.
// Fixes are different — no sky, no fix — so that limit is long and backs off
// while the silence lasts, and a re-request is cheap either way.
private const val WATCHDOG_PERIOD_MS = 5_000L
private const val SENSOR_SILENCE_BASE_MS = 5_000L
private const val SENSOR_SILENCE_MAX_MS = 60_000L

// The other way a registration dies: it keeps DELIVERING, at full rate, but
// every sample repeats one frozen attitude. Silence never trips, the EMA
// converges on the frozen value, and the elected bearing tracks it faithfully
// — the heading then answers only to the device-orientation remap, which
// reads as a compass alternating between a couple of values depending on how
// the phone is held. Requires evidence the phone MOVED (the orientation class
// changed, which the framework's own listener reports independently of our
// registration), so a phone lying still is never restarted for lying still.
private const val SENSOR_STUCK_MS = 12_000L
private const val SENSOR_STUCK_MAX_MS = 60_000L
private const val FIX_SILENCE_BASE_MS = 60_000L
private const val FIX_SILENCE_MAX_MS = 10 * 60_000L

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
    /**
     * Keep the sensors registered while the app is in the background. False
     * is the original's behaviour for capture and map viewing (pause on
     * background, resume on foreground — power); true is the external-camera
     * service, whose whole point is recording while ANOTHER app is in front,
     * and whose foreground service is what makes background sensors
     * permitted at all. The fix stream is not gated by this: it runs
     * whenever configured (the platform throttles it in the background
     * without a foreground service, and hands it back on return).
     */
    val sensorsInBackground: Boolean = false,
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
    // CONFIGURATION runs on the main thread: the process-lifecycle observer
    // below must be registered there (androidx enforces it — "Method
    // addObserver must be called on the main thread", caught on a device the
    // first time this ran) and its callbacks arrive there, so keeping every
    // start/stop on main is what makes them serialize without a lock.
    // Config changes are rare (an activity switch); samples are not.
    private val thread = HandlerThread("hillview-geo").apply { start() }
    private val handler = Handler(thread.looper)
    private val mainHandler = Handler(android.os.Looper.getMainLooper())

    private val geoTracking by lazy { GeoTrackingManager.get(context) }

    // Written on the main thread (configuration), read on the geo thread
    // (watchdog, the fix fan-out) — hence volatile.
    @Volatile private var sensorService: EnhancedSensorService? = null
    @Volatile private var locationService: PreciseLocationService? = null
    @Volatile private var active: GeoConfig = GeoConfig.Off

    // FOREGROUND/BACKGROUND IS THE ENGINE'S BUSINESS. The sensor service used
    // to pause and resume itself (its own ProcessLifecycleOwner observer,
    // observeAppLifecycle), and the fix stream was simply left registered
    // across a backgrounding — and the user kept coming back to a compass and
    // a GPS both frozen at their last values, with every consumer downstream
    // healthy. Whatever exactly the platform does to a backgrounded (and,
    // on modern Android, FROZEN) process's sensor and fused-location
    // registrations, the cure is the same: on every return to the
    // foreground, register afresh. So the engine observes the process
    // lifecycle itself, pauses sensors on background (unless the config says
    // otherwise), re-arms BOTH streams on foreground, and the watchdog below
    // catches the cases no lifecycle event announces.
    @Volatile private var foreground = true
    private var wasBackgrounded = false
    @Volatile private var sensorsStartedAtMs = 0L
    @Volatile private var locationStartedAtMs = 0L
    @Volatile private var lastFixAtMs = 0L
    @Volatile private var fixSilenceLimitMs = FIX_SILENCE_BASE_MS
    @Volatile private var sensorSilenceLimitMs = SENSOR_SILENCE_BASE_MS
    // Backs off like the silence limit: if a fresh registration comes back
    // just as frozen, retrying every twelve seconds forever helps nobody.
    @Volatile private var sensorStuckLimitMs = SENSOR_STUCK_MS
    @Volatile private var sensorRestarts = 0
    @Volatile private var fixRerequests = 0

    private val processObserver = object : DefaultLifecycleObserver {
        override fun onStart(owner: LifecycleOwner) = onForeground()
        override fun onStop(owner: LifecycleOwner) = onBackground()
    }

    private val watchdog = object : Runnable {
        override fun run() {
            try {
                checkLiveness()
            } catch (e: Exception) {
                Log.w(TAG, "watchdog failed", e)
            } finally {
                handler.postDelayed(this, WATCHDOG_PERIOD_MS)
            }
        }
    }

    init {
        // addObserver must run on main; an already-started process lifecycle
        // replays onStart at once, which is a harmless no-op here.
        mainHandler.post {
            val lifecycle = ProcessLifecycleOwner.get().lifecycle
            foreground = lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)
            lifecycle.addObserver(processObserver)
        }
        handler.postDelayed(watchdog, WATCHDOG_PERIOD_MS)
    }

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
                "sensors ${config.sensorDelayUs / 1000}ms, fixes ${config.locationIntervalMs}ms" +
                    (if (config.sensorsInBackground) " (sensors in background too)" else ""),
        )
        val previous = active
        active = config

        // Sensors: the rate is fixed at registration, so a change is a
        // restart; whether they run RIGHT NOW also depends on foreground.
        if (sensorService != null &&
            (!config.sensors || config.sensorDelayUs != previous.sensorDelayUs)
        ) {
            stopSensors()
        }
        syncSensors()

        // Location.
        val wantLocation = config.locationIntervalMs > 0
        val hadLocation = previous.locationIntervalMs > 0
        if (wantLocation && (!hadLocation || config.locationIntervalMs != previous.locationIntervalMs)) {
            stopLocation()
            startLocation()
        } else if (!wantLocation && hadLocation) {
            stopLocation()
        }
    }

    /** The one rule for whether the sensors are registered at this moment. */
    private fun sensorsWanted(): Boolean =
        active.sensors && (foreground || active.sensorsInBackground)

    private fun syncSensors() {
        if (sensorsWanted()) startSensors() else stopSensors()
    }

    private fun onBackground() {
        foreground = false
        wasBackgrounded = true
        val pausing = sensorService != null && !sensorsWanted()
        Log.i(TAG, "background (sensors ${if (pausing) "paused" else if (sensorService != null) "kept" else "off"})")
        cz.hillview.plugin.EventLog.record(
            "geo",
            "background — sensors " +
                (if (pausing) "paused" else if (sensorService != null) "kept running" else "off") +
                (if (locationService != null) ", fix stream left registered" else ""),
        )
        syncSensors()
    }

    private fun onForeground() {
        foreground = true
        // The replayed onStart at observer registration, and any start that
        // was not preceded by a stop: nothing to re-arm.
        if (!wasBackgrounded) return
        wasBackgrounded = false
        // RE-ARM, unconditionally: whatever the platform did to the old
        // registrations while we were away, a fresh one is known-good. The
        // sensors are torn down and re-registered even if the config kept
        // them running in the background; the fix stream is removed and
        // re-requested.
        val hadSensors = sensorService != null
        val hadLocation = locationService != null
        stopSensors()
        syncSensors()
        if (hadLocation) {
            stopLocation()
            startLocation()
        }
        Log.i(TAG, "foreground — re-armed (sensors=${sensorService != null} location=${locationService != null})")
        cz.hillview.plugin.EventLog.record(
            "geo",
            "foreground — " + listOfNotNull(
                if (sensorService != null) (if (hadSensors) "sensors re-registered" else "sensors started") else null,
                if (hadLocation) "fix stream re-requested" else null,
            ).joinToString(", ").ifEmpty { "nothing to re-arm" },
        )
    }

    /**
     * Runs on the geo thread every [WATCHDOG_PERIOD_MS]. Restarts go through
     * the main handler, where configuration lives.
     */
    private fun checkLiveness() {
        val now = SystemClock.elapsedRealtime()
        val sensors = sensorService
        // `running` false = the service itself could not register (no such
        // sensor, logged there); restarting would not change that.
        if (sensors != null && sensors.running && sensorsWanted()) {
            val raw = sensors.lastRawEventElapsedMs
            // A registration that has produced events is healthy: back to
            // the base limit. One that never has keeps backing off, so a
            // sensor the platform refuses outright is retried on a minute
            // cadence rather than every tick.
            if (raw > sensorsStartedAtMs) sensorSilenceLimitMs = SENSOR_SILENCE_BASE_MS
            // A sample that MOVED recently is proof the registration is
            // genuinely healthy, which the arrival of one is not.
            if (now - sensors.lastRawValueChangeElapsedMs < SENSOR_STUCK_MS) {
                sensorStuckLimitMs = SENSOR_STUCK_MS
            }
            val last = raw.takeIf { it != 0L } ?: sensorsStartedAtMs
            val silence = now - last
            val valueChange = sensors.lastRawValueChangeElapsedMs
            val stuck = sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = raw,
                valueChangeAtMs = valueChange,
                orientationChangeAtMs = sensors.lastOrientationChangeElapsedMs,
                stuckLimitMs = sensorStuckLimitMs,
            )
            if (silence <= sensorSilenceLimitMs && stuck) {
                sensorRestarts++
                val still = (now - valueChange) / 1000
                sensorStuckLimitMs = (sensorStuckLimitMs * 2).coerceAtMost(SENSOR_STUCK_MAX_MS)
                Log.w(TAG, "sensor value frozen ${still}s while the device turned — re-registering (#$sensorRestarts)")
                cz.hillview.plugin.EventLog.record(
                    "geo",
                    "attitude frozen ${still}s while the device turned — re-registered (#$sensorRestarts)",
                )
                CaptureStatsLog.increment("geo sensor restarts", System.currentTimeMillis())
                mainHandler.post {
                    if (sensorService === sensors) {
                        stopSensors()
                        syncSensors()
                    }
                }
            }
            if (silence > sensorSilenceLimitMs) {
                sensorRestarts++
                sensorSilenceLimitMs = (sensorSilenceLimitMs * 2).coerceAtMost(SENSOR_SILENCE_MAX_MS)
                Log.w(TAG, "sensors silent ${silence / 1000}s while wanted — re-registering (#$sensorRestarts)")
                cz.hillview.plugin.EventLog.record(
                    "geo",
                    "sensors silent ${silence / 1000}s — re-registered (#$sensorRestarts)",
                )
                CaptureStatsLog.increment("geo sensor restarts", System.currentTimeMillis())
                mainHandler.post {
                    if (sensorService === sensors) {
                        stopSensors()
                        syncSensors()
                    }
                }
            }
        }
        val location = locationService
        if (location != null && foreground) {
            val last = maxOf(lastFixAtMs, locationStartedAtMs)
            val silence = now - last
            if (silence > fixSilenceLimitMs) {
                fixRerequests++
                // Back off while the silence lasts (no sky is the common
                // case); a fix resets it.
                fixSilenceLimitMs = (fixSilenceLimitMs * 2).coerceAtMost(FIX_SILENCE_MAX_MS)
                Log.w(TAG, "no fix for ${silence / 1000}s — re-requesting (#$fixRerequests, next after ${fixSilenceLimitMs / 1000}s)")
                cz.hillview.plugin.EventLog.record(
                    "geo",
                    "no fix for ${silence / 1000}s — fix stream re-requested (#$fixRerequests)",
                )
                CaptureStatsLog.increment("geo fix re-requests", System.currentTimeMillis())
                mainHandler.post {
                    if (locationService === location) {
                        stopLocation()
                        startLocation()
                    }
                }
            }
        }
    }

    /**
     * How long the raw attitude has been REPEATING, for the debug readout —
     * null when there is nothing to say yet. Distinguishes a still phone
     * (short) from a frozen registration (long, while the phone turns).
     */
    fun sensorValueStillMs(): Long? {
        val at = sensorService?.lastRawValueChangeElapsedMs?.takeIf { it != 0L } ?: return null
        return SystemClock.elapsedRealtime() - at
    }

    /** One line for the Stats dialog: how alive each stream is right now. */
    fun livenessLine(): String {
        val now = SystemClock.elapsedRealtime()
        val sensors = sensorService
        val sensorAge = sensors?.lastRawEventElapsedMs?.takeIf { it != 0L }?.let { "${(now - it) / 1000}s ago" }
        val valueAge = sensors?.lastRawValueChangeElapsedMs?.takeIf { it != 0L }
            ?.let { ", value moved ${(now - it) / 1000}s ago" } ?: ""
        val fixAge = lastFixAtMs.takeIf { it != 0L }?.let { "${(now - it) / 1000}s ago" }
        return "geo: ${if (foreground) "foreground" else "background"}, " +
            "sensors " + (if (sensors == null) "off" else "raw event ${sensorAge ?: "never"}$valueAge") + ", " +
            "fix " + (if (locationService == null) "off" else (fixAge ?: "never")) +
            (if (sensorRestarts + fixRerequests > 0) ", restarts $sensorRestarts/$fixRerequests" else "")
    }

    private fun startSensors() {
        if (sensorService != null) return
        sensorsStartedAtMs = SystemClock.elapsedRealtime()
        sensorService = EnhancedSensorService(
            context = context,
            callbackHandler = handler,
            // The engine pauses, resumes and re-arms — see the foreground
            // notes above; a second actor inside the service would fight it.
            observeAppLifecycle = false,
        ) { data ->
            // One sample, fanned out — the plugin's shape exactly.
            geoTracking.storeOrientationSensorData(data)
            _orientation.value = data
        }.also { it.startSensor() }
    }

    private fun stopSensors() {
        sensorService?.let {
            try {
                // destroy, not stop: stop is a pause that leaves the
                // instance's lifecycle hooks registered.
                it.destroy()
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
        locationStartedAtMs = SystemClock.elapsedRealtime()
        fixSilenceLimitMs = FIX_SILENCE_BASE_MS
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
        lastFixAtMs = SystemClock.elapsedRealtime()
        fixSilenceLimitMs = FIX_SILENCE_BASE_MS
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
