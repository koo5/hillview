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

private const val TAG = "hv-GeoEngine"

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

// How many times to re-register before accepting that re-registering is not
// the cure. Past this the engine stops trying until something real changes
// (a return to the foreground, an activity's config), because the failure
// mode being defended against here is not ours alone: a sensor hub can wedge
// for the WHOLE DEVICE — every app's compass stuck at once — and churning
// registrations at a wedged hub is the one thing that could be making it
// worse. A watchdog that never gives up is a busy loop with a long period.
private const val SENSOR_RESTART_GIVE_UP = 5

/** The visible activity's claim on the hardware — see GeoEngine.claims. */
const val OWNER_ACTIVITY = "activity"

/** The external-camera foreground service's, which outlives the pane. */
const val OWNER_EXTERNAL_SERVICE = "external-service"
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
    /**
     * Keep a high-rate accelerometer + gyroscope ring buffer, so a capture can
     * persist the window around its exposure.
     *
     * OFF for map viewing, deliberately. This is the one stream registered at
     * SENSOR_DELAY_FASTEST, because a window has to describe a shutter and 10 Hz
     * cannot; nothing about looking at a map needs that, and the battery cost
     * belongs only to the activities that produce photos.
     */
    val imu: Boolean = false,
    /**
     * Persist EVERY sample, not just the windows around this app's own shutters.
     *
     * For the external-camera activity, where another app takes the photos and
     * nothing here fires a shutter to trigger a window — so without this that
     * mode records no inertial data at all, which is the one mode a whole drive
     * might be spent in.
     *
     * FULL RATE, not decimated (user, 2026-09-26: "i totally want non-decimate,
     * full-frequency sampling for external camera activity, there are
     * experiments that we will run on the samples, such as shutter detection").
     * That is the right call for that purpose and it is worth being explicit
     * about the price: a mechanical shutter is a transient a few milliseconds
     * long, so 50 or 100 Hz would alias it away entirely and the experiment
     * could not run at all. At a few hundred hertz across two sensors this is
     * on the order of 100 MB of CSV an hour, which is why it is a user-visible
     * toggle and not a silent default.
     */
    val imuContinuous: Boolean = false,
) {
    companion object {
        val Off = GeoConfig(sensors = false, sensorDelayUs = 0, locationIntervalMs = 0)
    }
}

/**
 * ±ms around the exposure the IMU window covers — see GeoEngine.persistImuWindow.
 *
 * THREE seconds each way (user, 2026-09-26), not the half-second it started at.
 * The reason is not the exposure, which a tenth of a second covers: it is that
 * interval capture at a few seconds a shot then produces windows that BUTT
 * AGAINST each other, and with the overlap trimmed (see `imuHighWaterMs`) they
 * concatenate into one continuous inertial record of the whole shoot. That is a
 * different and much more valuable artifact than a bag of per-photo snippets.
 *
 * It also means a window is only COMPLETE three seconds after the shutter, so
 * the capture path cannot persist it inline — see the deferred call, which
 * follows the StampRefiner's existing "wait for the window to close, then read"
 * pattern and fits inside the upload hold it already takes.
 */
const val IMU_WINDOW_HALF_MS = 3_000L

/** Margin past the window's end before reading it — IO and main-thread hops. */
const val IMU_SETTLE_MARGIN_MS = 150L

/**
 * How often continuous mode drains the ring to the table.
 *
 * A row per sample at a few hundred hertz would be a write every two
 * milliseconds; batching a second at a time turns that into one insert of a few
 * hundred rows, which is what SQLite is good at. The ring holds far more than a
 * second, so nothing is lost between drains.
 */
const val IMU_FLUSH_PERIOD_MS = 1_000L

/** m/s², for turning a raw accelerometer magnitude into a gravity-free deviation. */
const val STANDARD_GRAVITY = 9.80665

/**
 * What the IMU window around one shutter contained — the summary that travels
 * in the upload's `motion` object, so a server-side reader gets the quality
 * signal without needing the CSV the samples themselves go to.
 */
data class ImuWindowSummary(
    val sampleCount: Int,
    val startMs: Long,
    val endMs: Long,
    /** Peak raw accelerometer magnitude, m/s². INCLUDES gravity (~9.81 at rest). */
    val accelPeakMps2: Double? = null,
    /**
     * Peak |magnitude − g|, m/s² — the gravity-free shake signal, derived from
     * the raw accelerometer rather than needing the linear-acceleration sensor.
     * Near zero for a still phone however it is oriented.
     */
    val accelPeakDeviationMps2: Double? = null,
    /** Peak angular rate, rad/s. The rotation-blur signal, and gravity-free by nature. */
    val gyroPeakRadS: Double? = null,
    /**
     * How many of [sampleCount] this capture actually wrote to the table — the
     * rest a neighbouring photo's window had already stored. See
     * `GeoEngine.imuHighWaterMs`; with interval capture this is roughly the
     * interval's worth rather than the window's.
     */
    val storedCount: Int = 0,
)

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
    // Restarts since the sensor was last demonstrably healthy (a sample that
    // MOVED — an arriving one proves nothing, see sensorLooksStuck).
    @Volatile private var sensorRestartsWithoutRecovery = 0
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

    /**
     * Gravity and linear acceleration, latest sample — the INERTIAL half of
     * how the phone was held.
     *
     * Its own registration, because [EnhancedSensorService] does not register
     * either sensor in the mode this app runs (UPRIGHT_ROTATION_VECTOR takes
     * the magnetometer and the rotation vector), and because the engine is the
     * one place allowed to open a sensor at all.
     *
     * Why both, when pitch and roll exist: `TYPE_GRAVITY` is an unambiguous
     * "down" in the device frame, where the published pitch and roll come out
     * of a matrix ALREADY remapped for the quantized device pose and are
     * therefore residuals within a quadrant. Gravity constrains two rotation
     * degrees of freedom on its own, which is what a reconstruction wants.
     * `TYPE_LINEAR_ACCELERATION` is the same stream with gravity removed, so
     * its magnitude is how hard the phone was actually being moved — the cheap
     * per-frame motion-blur signal, and the thing a single raw accelerometer
     * sample can never give, because one such sample conflates the two
     * inseparably.
     */
    private val _motion = MutableStateFlow<cz.hillview.map.DeviceMotionSample?>(null)
    val motion: StateFlow<cz.hillview.map.DeviceMotionSample?> = _motion.asStateFlow()

    /** True while the fix stream is meant to be running (permission-gated). */
    private val _locationActive = MutableStateFlow(false)
    val locationActive: StateFlow<Boolean> = _locationActive.asStateFlow()

    /**
     * Who is asking for the hardware, and for what.
     *
     * There is more than one asker — the visible activity, and the
     * external-camera foreground service that has to outlive it — and until
     * this existed they simply took turns writing one global config, last
     * writer wins. That is a race with a nasty landing: leaving the external
     * pane for capture, MainScreen configures capture and the SERVICE's
     * onDestroy then configures Off, in whichever order the system happens
     * to destroy the service. Win, and the compass works; lose, and the
     * sensors stop while the capture pane sits in front of you with its
     * heading frozen and its sample age climbing, until some other activity
     * change happens to fix it. "Sometimes it works" is the signature of it.
     *
     * So an owner cannot turn the hardware off any more — it can only stop
     * asking, and what runs is the union of what is still being asked for.
     */
    private val claims = LinkedHashMap<String, GeoConfig>()

    /**
     * Apply a configuration. Idempotent: the same config twice is a no-op, so
     * a recomposing caller can hand it over freely.
     *
     * [GeoConfig.Off] means "I no longer need anything", not "nobody does" —
     * it drops this owner's claim and leaves everyone else's standing.
     */
    @JvmOverloads
    fun configure(config: GeoConfig, owner: String = OWNER_ACTIVITY) {
        mainHandler.post {
            if (config == GeoConfig.Off) claims.remove(owner) else claims[owner] = config
            applyConfig(mergedConfig())
        }
    }

    /** Stop asking. The hardware keeps running for whoever else still is. */
    fun release(owner: String) {
        mainHandler.post {
            claims.remove(owner)
            applyConfig(mergedConfig())
        }
    }

    /**
     * The union: sensors on if anyone wants them, at the FASTEST rate asked
     * for (a slower claim is satisfied by a faster stream; the reverse is
     * not), fixes likewise, and background operation if any claim needs it.
     */
    private fun mergedConfig(): GeoConfig {
        if (claims.isEmpty()) return GeoConfig.Off
        val wantSensors = claims.values.filter { it.sensors }
        val intervals = claims.values.map { it.locationIntervalMs }.filter { it > 0 }
        return GeoConfig(
            sensors = wantSensors.isNotEmpty(),
            sensorDelayUs = wantSensors.minOfOrNull { it.sensorDelayUs } ?: 0,
            locationIntervalMs = intervals.minOrNull() ?: 0L,
            sensorsInBackground = claims.values.any { it.sensorsInBackground },
            imu = claims.values.any { it.imu },
            imuContinuous = claims.values.any { it.imuContinuous },
        )
    }

    /** Car mode's heading filter is stateful — the map resets it on entry. */
    fun resetCarHeadingFilter() {
        handler.post { geoTracking.resetHeadingFilter() }
    }

    private fun applyConfig(config: GeoConfig) {
        if (config == active) return
        // A real change in what the app is doing: worth trying the hardware
        // again even if the watchdog had given up on it.
        sensorRestartsWithoutRecovery = 0
        Log.i(TAG, "configure $active -> $config")
        cz.hillview.plugin.EventLog.record(
            "geo",
            "engine -> " + if (!config.sensors && config.locationIntervalMs == 0L) "off" else
                "sensors ${config.sensorDelayUs / 1000}ms, fixes ${config.locationIntervalMs}ms" +
                    (if (config.sensorsInBackground) " (sensors in background too)" else ""),
        )
        val previous = active
        active = config

        // The IMU ring follows the claim: an activity that stops asking for
        // it releases the fastest registration the app makes.
        if (!config.imu) stopImuSensors() else if (sensorService != null) startImuSensors()

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
        // Coming back to the foreground is the other event worth a fresh
        // attempt — much of what wedges a registration is a backgrounding.
        sensorRestartsWithoutRecovery = 0
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
            if (sensors.lastRawValueChangeElapsedMs != 0L &&
                now - sensors.lastRawValueChangeElapsedMs < SENSOR_STUCK_MS
            ) {
                sensorStuckLimitMs = SENSOR_STUCK_MS
                sensorRestartsWithoutRecovery = 0
            }
            val last = raw.takeIf { it != 0L } ?: sensorsStartedAtMs
            val silence = now - last
            val valueChange = sensors.lastRawValueChangeElapsedMs
            if (sensorRestartsWithoutRecovery == SENSOR_RESTART_GIVE_UP) {
                sensorRestartsWithoutRecovery++ // once, so this logs once
                Log.w(TAG, "re-registering has not revived the sensors — standing down until foreground or config change")
                cz.hillview.plugin.EventLog.record(
                    "geo",
                    "sensors did not revive after $SENSOR_RESTART_GIVE_UP re-registrations — " +
                        "standing down (a device-wide sensor stall looks like this; " +
                        "check whether other apps' compasses are stuck too)",
                )
            }
            val stuck = sensorLooksStuck(
                nowMs = now,
                rawEventAtMs = raw,
                valueChangeAtMs = valueChange,
                orientationChangeAtMs = sensors.lastOrientationChangeElapsedMs,
                stuckLimitMs = sensorStuckLimitMs,
            )
            if (silence <= sensorSilenceLimitMs && stuck &&
                sensorRestartsWithoutRecovery < SENSOR_RESTART_GIVE_UP
            ) {
                sensorRestarts++
                sensorRestartsWithoutRecovery++
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
            if (silence > sensorSilenceLimitMs &&
                sensorRestartsWithoutRecovery < SENSOR_RESTART_GIVE_UP
            ) {
                sensorRestarts++
                sensorRestartsWithoutRecovery++
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

    /** The device-orientation class the UPRIGHT remap is keyed on. */
    fun deviceOrientationName(): String? = sensorService?.deviceOrientationName

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
            ", registrations $sensorStarts" +
            (if (sensorRestarts + fixRerequests > 0) ", restarts $sensorRestarts/$fixRerequests" else "")
    }

    // Every registerListener this process has ever asked for. Churn is the
    // thing to watch when a sensor hub stalls device-wide, and "how many
    // times did we register today" is the first number anyone would want.
    @Volatile private var sensorStarts = 0

    /**
     * Gravity and linear acceleration, registered and published as one sample.
     *
     * Both arrive on their own callbacks, so the latest of each is held and the
     * pair is published whenever either moves — with the timestamp of the
     * sample that triggered it, so staleness is measurable rather than assumed.
     */
    private val motionListener = object : android.hardware.SensorEventListener {
        @Volatile private var gravity: List<Float>? = null
        @Volatile private var linear: List<Float>? = null

        override fun onSensorChanged(event: android.hardware.SensorEvent) {
            when (event.sensor.type) {
                android.hardware.Sensor.TYPE_GRAVITY ->
                    gravity = listOf(event.values[0], event.values[1], event.values[2])
                android.hardware.Sensor.TYPE_LINEAR_ACCELERATION ->
                    linear = listOf(event.values[0], event.values[1], event.values[2])
                else -> return
            }
            _motion.value = cz.hillview.map.DeviceMotionSample(
                gravity = gravity,
                linearAcceleration = linear,
                atMs = System.currentTimeMillis(),
            )
        }

        override fun onAccuracyChanged(sensor: android.hardware.Sensor?, accuracy: Int) {}

        fun reset() {
            gravity = null
            linear = null
        }
    }

    @Volatile private var motionRegistered = false

    private fun startMotionSensors() {
        if (motionRegistered) return
        val manager = context.getSystemService(Context.SENSOR_SERVICE) as? android.hardware.SensorManager
            ?: return
        // Absent on some devices, and absence is not an error: the fields stay
        // null and the stamp says nothing rather than guessing.
        val wanted = listOfNotNull(
            manager.getDefaultSensor(android.hardware.Sensor.TYPE_GRAVITY),
            manager.getDefaultSensor(android.hardware.Sensor.TYPE_LINEAR_ACCELERATION),
        )
        if (wanted.isEmpty()) {
            Log.w(TAG, "no gravity / linear-acceleration sensor on this device")
            return
        }
        wanted.forEach { manager.registerListener(motionListener, it, active.sensorDelayUs, handler) }
        motionRegistered = true
        Log.i(TAG, "motion sensors registered (${wanted.joinToString { it.name }})")
    }

    private fun stopMotionSensors() {
        if (!motionRegistered) return
        (context.getSystemService(Context.SENSOR_SERVICE) as? android.hardware.SensorManager)
            ?.unregisterListener(motionListener)
        motionRegistered = false
        motionListener.reset()
        // Nothing is measuring it any more, so stop claiming a value: a stale
        // gravity vector under a fresh shutter is the `0f` mistake again.
        _motion.value = null
    }

    // Sized so the DEFERRED read still finds the whole window: 6 s of it plus a
    // settle margin, two sensors, at a SENSOR_DELAY_FASTEST rate that reaches a
    // few hundred hertz on a fast phone — call it 1 000 samples a second, so
    // 16 000 slots is about sixteen seconds of headroom. ~450 KB of primitive
    // arrays. A buffer that wrapped mid-window would silently return half of
    // one, which is the failure that looks like data rather than an error.
    private val imuRing = ImuRing(capacity = 16_000)

    /**
     * The newest sample already persisted, so consecutive windows do not store
     * the same samples twice (user, 2026-09-26: "take note of the last sample
     * stored with last photo, so the next photo does not overlap it
     * unnecessarily").
     *
     * With interval capture the windows overlap heavily — a 2 s interval and a
     * ±3 s window means 4 s of every 6 s is shared with a neighbour. Trimmed,
     * the photos' windows tile the session instead of repeating it, and what
     * reaches the workbench is one trajectory rather than N overlapping copies
     * of most of it.
     *
     * The SUMMARY is still computed over the whole window: what a frame was
     * doing does not depend on which of its samples a neighbour happened to
     * store first.
     */
    @Volatile private var imuHighWaterMs: Long = 0L

    private val imuListener = object : android.hardware.SensorEventListener {
        override fun onSensorChanged(event: android.hardware.SensorEvent) {
            val kind = when (event.sensor.type) {
                android.hardware.Sensor.TYPE_ACCELEROMETER -> ImuRing.KIND_ACCEL
                android.hardware.Sensor.TYPE_GYROSCOPE -> ImuRing.KIND_GYRO
                else -> return
            }
            val atMs = System.currentTimeMillis()
            imuRing.add(
                atMs, event.timestamp, kind,
                event.values[0], event.values[1], event.values[2],
            )
            // Continuous mode (external camera): every sample to the table, at
            // full rate. Batched through the ring rather than inserted one at a
            // time — a row per sample at a few hundred hertz would be a write
            // per 2 ms, and SQLite would spend the session in transaction
            // overhead.
            if (active.imuContinuous && atMs - lastContinuousFlushMs >= IMU_FLUSH_PERIOD_MS) {
                lastContinuousFlushMs = atMs
                flushContinuousImu(atMs)
            }
        }

        override fun onAccuracyChanged(sensor: android.hardware.Sensor?, accuracy: Int) {}
    }

    @Volatile private var imuRegistered = false
    @Volatile private var lastContinuousFlushMs = 0L

    /**
     * Drain everything not yet stored, up to [upToMs]. Continuous mode only.
     *
     * Shares [imuHighWaterMs] with the per-capture path on purpose: whichever
     * wrote a sample first, it is written ONCE, so a session that is partly
     * external and partly capture does not double-store its overlap.
     */
    private fun flushContinuousImu(upToMs: Long) {
        val fresh = imuRing.window(imuHighWaterMs + 1, upToMs)
        if (fresh.isEmpty()) return
        geoTracking.storeImuSamples(fresh)
        imuHighWaterMs = fresh.last().timestamp
    }

    private fun startImuSensors() {
        if (imuRegistered || !active.imu) return
        val manager = context.getSystemService(Context.SENSOR_SERVICE) as? android.hardware.SensorManager
            ?: return
        val wanted = listOfNotNull(
            manager.getDefaultSensor(android.hardware.Sensor.TYPE_ACCELEROMETER),
            manager.getDefaultSensor(android.hardware.Sensor.TYPE_GYROSCOPE),
        )
        if (wanted.isEmpty()) {
            Log.w(TAG, "no accelerometer / gyroscope — no IMU windows on this device")
            return
        }
        // FASTEST, unlike the other registrations: the point of a window is the
        // shape of the signal across an exposure, and 10 Hz cannot describe a
        // 1/60 s shutter. This is the one stream whose rate is set by what it is
        // FOR rather than by the activity's power budget — which is exactly why
        // it is behind GeoConfig.imu and off for map viewing.
        wanted.forEach {
            manager.registerListener(
                imuListener, it, android.hardware.SensorManager.SENSOR_DELAY_FASTEST, handler,
            )
        }
        imuRegistered = true
        Log.i(TAG, "IMU ring registered (${wanted.joinToString { s -> s.name }})")
    }

    private fun stopImuSensors() {
        if (!imuRegistered) return
        (context.getSystemService(Context.SENSOR_SERVICE) as? android.hardware.SensorManager)
            ?.unregisterListener(imuListener)
        imuRegistered = false
        imuRing.clear()
    }

    /**
     * Persist the IMU window [fromMs]..[toMs] and return what it contained.
     *
     * Returns null when the window is empty, which is the honest answer on a
     * device with no gyroscope, in an activity that did not ask for the IMU, or
     * for a capture taken before the buffer had filled.
     *
     * A method rather than a flow: a few-hundred-hertz buffer is not
     * user-facing state and has no business passing through recomposition.
     */
    fun persistImuWindow(fromMs: Long, toMs: Long): ImuWindowSummary? {
        val samples = imuRing.window(fromMs, toMs)
        if (samples.isEmpty()) return null
        // Store only what a neighbour has not already stored; summarise ALL of
        // it. See imuHighWaterMs.
        val fresh = samples.filter { it.timestamp > imuHighWaterMs }
        if (fresh.isNotEmpty()) {
            geoTracking.storeImuSamples(fresh)
            imuHighWaterMs = fresh.last().timestamp
        }
        val accel = samples.filter { it.kind == "accel" }
        val gyro = samples.filter { it.kind == "gyro" }
        fun magnitude(s: cz.hillview.plugin.ImuSampleEntity) =
            kotlin.math.sqrt(
                (s.x.toDouble() * s.x + s.y.toDouble() * s.y + s.z.toDouble() * s.z),
            )
        val accelMagnitudes = accel.map(::magnitude)
        return ImuWindowSummary(
            sampleCount = samples.size,
            startMs = samples.first().timestamp,
            endMs = samples.last().timestamp,
            /** What this photo actually ADDED to the table — see imuHighWaterMs. */
            storedCount = fresh.size,
            // Raw accelerometer INCLUDES gravity, so this sits near 9.81 on a
            // still phone. Reported as-is, and the deviation below is the
            // gravity-free shake signal derived from it.
            accelPeakMps2 = accelMagnitudes.maxOrNull(),
            accelPeakDeviationMps2 = accelMagnitudes
                .maxOfOrNull { kotlin.math.abs(it - STANDARD_GRAVITY) },
            gyroPeakRadS = gyro.map(::magnitude).maxOrNull(),
        )
    }

    /**
     * Persist the SYMMETRIC window around an exposure, once its later half has
     * happened, and hand the summary back.
     *
     * Deferred because half the window is in the future at the shutter. Two
     * things settled which half matters, and they point the same way:
     *
     *  - **The press is not the exposure.** `capturedAtMs` is when the button
     *    went down; the camera starts exposing measurably later (the capture
     *    path logs `press→exp`, and in Quality mode the 3A lock can make that
     *    approach a second). A window ending at the press therefore contains
     *    none of the exposure — which is the wrong half for motion blur, and
     *    useless for detecting a shutter in the signal.
     *  - **With butt-to-butt trimming the two are nearly the same anyway**
     *    (user's own reasoning, 2026-09-26): in an interval run below 6 s the
     *    previous photo's window has already claimed everything before this
     *    shutter, so each photo stores post-shutter samples regardless, and only
     *    an interval over 6 s yields a genuinely symmetric window per photo.
     *    Which is a reason not to fear the deferral, not a reason to skip it.
     *
     * The wait needs no machinery of its own: the ring holds well over six
     * seconds, so the later half is simply still there when this runs.
     */
    fun persistImuWindowAround(
        centreAtMs: Long,
        halfWidthMs: Long = IMU_WINDOW_HALF_MS,
        onReady: (ImuWindowSummary?) -> Unit = {},
    ) {
        val readAt = centreAtMs + halfWidthMs + IMU_SETTLE_MARGIN_MS
        val delayMs = (readAt - System.currentTimeMillis()).coerceAtLeast(0)
        handler.postDelayed(
            { onReady(persistImuWindow(centreAtMs - halfWidthMs, centreAtMs + halfWidthMs)) },
            delayMs,
        )
    }

    /**
     * The window a SHUTTER can have INLINE: the [IMU_WINDOW_HALF_MS] before the
     * exposure, and nothing after it.
     *
     * The symmetric ±window this constant describes cannot be taken inline,
     * because half of it has not happened yet. Taking the past half and calling
     * it the window would be a silent half-measurement, so the asymmetry is in
     * the name and in what the summary reports.
     *
     * The symmetric version wants the deferred read the StampRefiner already
     * does for the compass (delay until the window closes, then read) and the
     * continuous persistence that makes the future half available to it — see
     * docs/recon-capture-metadata.md, "the deferred window".
     */
    fun persistImuWindowBeforeShutter(centreAtMs: Long): ImuWindowSummary? =
        persistImuWindow(centreAtMs - IMU_WINDOW_HALF_MS, centreAtMs)

    private fun startSensors() {
        startMotionSensors()
        startImuSensors()
        if (sensorService != null) return
        sensorsStartedAtMs = SystemClock.elapsedRealtime()
        sensorStarts++
        sensorService = EnhancedSensorService(
            context = context,
            callbackHandler = handler,
            // The engine pauses, resumes and re-arms — see the foreground
            // notes above; a second actor inside the service would fight it.
            observeAppLifecycle = false,
            // The rate the ACTIVITY asked for. Until this was passed, the
            // service registered at its own constant and GeoConfig's rate
            // only ever decided whether to restart the sensors — so every
            // activity switch tore the registration down and rebuilt an
            // identical one, and the relaxed map-only rate never ran.
            sensorDelayUs = active.sensorDelayUs,
        ) { data ->
            // One sample, fanned out — the plugin's shape exactly.
            geoTracking.storeOrientationSensorData(data)
            _orientation.value = data
        }.also { it.startSensor() }
    }

    private fun stopSensors() {
        stopMotionSensors()
        stopImuSensors()
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
        // The three ERROR BARS the platform gives and this conversion used to
        // drop on the floor (2026-09-26). PreciseLocationData has carried them
        // since it was written; Location has setters for all three; nobody
        // connected the two, so vertical/speed/bearing accuracy died here — one
        // hop before the one state, which had no fields for them either.
        altitudeAccuracy?.let { a -> it.verticalAccuracyMeters = a }
        speedAccuracy?.let { a -> it.speedAccuracyMetersPerSecond = a }
        bearingAccuracy?.let { a -> it.bearingAccuracyDegrees = a }
    }
