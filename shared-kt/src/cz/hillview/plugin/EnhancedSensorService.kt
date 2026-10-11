package cz.hillview.plugin

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.GeomagneticField
import android.location.Location
import android.os.SystemClock
import android.location.LocationManager
import android.os.Process
import android.util.Log
import android.view.OrientationEventListener
import android.view.Surface
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlin.math.*

enum class DeviceOrientation {
	FLAT_UP,
	FLAT_DOWN,
    PORTRAIT,
    LANDSCAPE_LEFT,  // 90° counter-clockwise, home button on right
    LANDSCAPE_RIGHT, // 90° clockwise, home button on left
    PORTRAIT_INVERTED; // 180° rotation, upside down

    companion object {
        fun fromDegrees(degrees: Int): DeviceOrientation = when {
            degrees == OrientationEventListener.ORIENTATION_UNKNOWN -> FLAT_UP
            degrees in 315..359 || degrees in 0..44 -> PORTRAIT // 0°
            degrees in 45..134 -> LANDSCAPE_LEFT // 90°
            degrees in 135..224 -> PORTRAIT_INVERTED // 180°
            degrees in 225..314 -> LANDSCAPE_RIGHT // 270°
            else -> PORTRAIT // Fallback
        }

		fun toExifCode(orientation: DeviceOrientation): Int = when (orientation) {
			PORTRAIT -> 1
			LANDSCAPE_LEFT -> 6
			PORTRAIT_INVERTED -> 3
			LANDSCAPE_RIGHT -> 8
			else -> throw IllegalArgumentException("Unsupported orientation for EXIF code: $orientation")
		}

		/**
		 * The device's own rotation in degrees, in the frame
		 * OrientationEventListener reports: 0 natural, 90 turned clockwise
		 * (left edge up), 180 inverted, 270 counter-clockwise.
		 *
		 * Unlike toExifCode this does NOT throw on the flat poses — a stale
		 * number beats a crash in the shutter path. Callers that care get
		 * the last non-flat pose anyway: MyDeviceOrientationSensor filters
		 * FLAT_UP/FLAT_DOWN before it ever reports a change.
		 */
		fun toDegrees(orientation: DeviceOrientation): Int = when (orientation) {
			PORTRAIT -> 0
			LANDSCAPE_LEFT -> 90
			PORTRAIT_INVERTED -> 180
			LANDSCAPE_RIGHT -> 270
			FLAT_UP, FLAT_DOWN -> 0
		}

		/**
		 * The Surface rotation the display WOULD have if it followed the
		 * device — which is what CameraX's ImageCapture.targetRotation
		 * wants, and from which CameraX derives the JPEG's EXIF Orientation.
		 *
		 * Deliberately NOT Display.getRotation(): that is the SCREEN's
		 * orientation, and it freezes under an auto-rotate lock (or an
		 * activity orientation lock) while the device keeps turning. Keeping
		 * the two apart is the same distinction the Tauri plugin draws
		 * between its `device-orientation` and `screen-angle` events — only
		 * the frames differ downstream: the webview's canvas frames arrive
		 * already display-oriented (so the JS side subtracts the screen
		 * angle), while CameraX buffers arrive in the raw sensor frame, so
		 * the pure device pose goes straight through.
		 *
		 * Note the inversion: turning the phone clockwise turns the display
		 * counter-clockwise relative to it.
		 */
		fun toSurfaceRotation(orientation: DeviceOrientation): Int =
			when (toDegrees(orientation)) {
				90 -> Surface.ROTATION_270
				180 -> Surface.ROTATION_180
				270 -> Surface.ROTATION_90
				else -> Surface.ROTATION_0
			}
    }
}

// Extension function for float formatting
private fun Float.format(digits: Int) = "%.${digits}f".format(this)

/**
 * Enhanced sensor service that provides more accurate bearing information
 * when the phone is upright by using multiple sensor fusion techniques.
 */
class EnhancedSensorService(
    private val context: Context,
    // Where SensorManager delivers events. Null = the main looper, which is
    // what registerListener(listener, sensor, delay) has always meant here,
    // so existing callers are unchanged. frontend2's GeoEngine passes its own
    // HandlerThread handler — at ~33 Hz these callbacks are the app's most
    // frequent, and they must not share a queue with map drawing.
    //
    // Declared BEFORE onSensorUpdate deliberately: every existing call site
    // passes the callback as a trailing lambda, which binds to the LAST
    // parameter — putting this one last silently rebound them to the handler.
    private val callbackHandler: android.os.Handler? = null,
    // Whether this instance pauses/resumes ITSELF on app background/foreground
    // and screen off/on (the AppLifecycleObserver below). True = the Tauri
    // plugin's behaviour, unchanged. frontend2's GeoEngine passes false: it
    // owns the hardware's lifetime, re-arms both sensors and the fix stream
    // on every return to the foreground, and runs a liveness watchdog — two
    // actors pausing and resuming the same listener is how a resume gets
    // lost. (Also BEFORE onSensorUpdate, for the trailing-lambda reason above.)
    private val observeAppLifecycle: Boolean = true,
    /**
     * The sampling period handed to registerListener, microseconds.
     *
     * It is a PARAMETER because the rate is a policy the owner decides —
     * frontend2's GeoConfig has carried a per-activity rate (a relaxed one
     * for map-only viewing, a normal one for capture) since the engine was
     * written, and it never reached the hardware: registration used the
     * constant below regardless, so the relaxed rate did not exist and a
     * config change restarted the sensors to arrive at the identical
     * registration. Registration churn is the thing to avoid on a device
     * whose sensor hub can wedge, and churn that changes nothing is the
     * worst kind. The default keeps the Tauri plugin's behaviour exactly.
     */
    private val sensorDelayUs: Int = DEFAULT_SENSOR_DELAY_US,
    /**
     * EVERY sample, before the per-mode rate limit that [onSensorUpdate] is behind.
     *
     * The published stream is capped at [MODE_RATE_LIMITS] — 200 ms in UPRIGHT mode —
     * because that is what a compass needle and the tracking rows want. A photo wants
     * something else: the attitude at the instant the shutter opened, and with a 200 ms
     * cap the nearest sample is up to 100 ms away, which is exactly what 32 uploaded
     * photos measured (|mean| 50 ms, worst 94). This tap exists so the capture's lookup
     * ring can be fed at the sensor's own rate while the cap keeps doing its job for the
     * UI and the CSVs.
     *
     * Null for callers that do not need it — the Tauri plugin's behaviour is unchanged.
     * Called on the same thread as [onSensorUpdate], so it must be cheap: a ring append,
     * nothing more.
     *
     * Declared BEFORE onSensorUpdate for the trailing-lambda reason spelled out above.
     */
    private val onRawSample: ((OrientationSensorData) -> Unit)? = null,
    private val onSensorUpdate: (OrientationSensorData) -> Unit,
) : SensorEventListener {
    companion object {
        private val TAG = hvTag("Sensors")
        private const val UPDATE_RATE_MS = 10 // Higher frequency for better fusion
        // The historical rate, kept as the default for callers that do not
        // choose one (the Tauri plugin).
        const val DEFAULT_SENSOR_DELAY_US = 1000*30//SensorManager.SENSOR_DELAY_GAME // Faster updates

        // Smoothing and filtering parameters
        /** How often the temporary frame-probe may write an Event log line. */
        private const val REVERSAL_PROBE_PERIOD_MS = 2_000L

        private const val EMA_ALPHA = 1f // EMA smoothing factor (0.1-0.3 range, lower = more smoothing)
        private const val HEADING_THRESHOLD = 1.0f // Minimum heading change to trigger update (degrees)
        private const val PITCH_THRESHOLD = 1.0f // Minimum pitch change to trigger update (degrees)
        private const val ROLL_THRESHOLD = 1.0f // Minimum roll change to trigger update (degrees)
        private const val ACCURACY_THRESHOLD = 1.0

        // Sensor fusion modes
        const val MODE_ROTATION_VECTOR = 0
        const val MODE_GAME_ROTATION_VECTOR = 1
        const val MODE_MADGWICK_AHRS = 2
        const val MODE_COMPLEMENTARY_FILTER = 3
        const val MODE_UPRIGHT_ROTATION_VECTOR = 4

        // Mode names for logging
        private val MODE_NAMES = mapOf(
            MODE_ROTATION_VECTOR to "ROTATION_VECTOR",
            MODE_GAME_ROTATION_VECTOR to "GAME_ROTATION_VECTOR",
            MODE_MADGWICK_AHRS to "MADGWICK_AHRS",
            MODE_COMPLEMENTARY_FILTER to "COMPLEMENTARY_FILTER",
            MODE_UPRIGHT_ROTATION_VECTOR to "UPRIGHT_ROTATION_VECTOR"
        )

        // Rate limits per mode (milliseconds between updates)
        private val MODE_RATE_LIMITS = mapOf(
            MODE_ROTATION_VECTOR to 300,          // 10 Hz
            MODE_GAME_ROTATION_VECTOR to 350,     // ~6.7 Hz (more aggressive limiting)
            MODE_MADGWICK_AHRS to 50,             // 20 Hz (needs higher rate for fusion)
            MODE_COMPLEMENTARY_FILTER to 200,     // 10 Hz
            MODE_UPRIGHT_ROTATION_VECTOR to 200   // 10 Hz
        )
    }

    private val sensorManager: SensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val locationManager: LocationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    // Available sensors
    private var rotationVectorSensor: Sensor? = null
    private var gameRotationVectorSensor: Sensor? = null
    private var geomagneticRotationVectorSensor: Sensor? = null
    private var accelerometerSensor: Sensor? = null
    private var gyroscopeSensor: Sensor? = null
    private var magnetometerSensor: Sensor? = null
    private var headingSensor: Sensor? = null
    private var poseSensor: Sensor? = null

    // Sensor fusion algorithms
    private val madgwickAHRS = MadgwickAHRS(sampleFreq = 50f, beta = 0.1f)

    // Thread priority management
    // Read and written on whichever thread the boost lands on, which is no
    // longer the caller's — hence volatile.
    @Volatile private var originalThreadPriority: Int? = null

    // Sensor data buffers
    private var accelerometerData = FloatArray(3)
    private var gravityData = FloatArray(3)
    private var hasGravity = false
    private var gyroscopeData = FloatArray(3)
    private var magnetometerData = FloatArray(3)
    private var hasAccelerometer = false
    private var hasGyroscope = false
    private var hasMagnetometer = false

    // Complementary filter state
    private var complementaryAngle = 0f
    private var lastComplementaryUpdate = 0L

    // Calibration state
    private var magnetometerCalibrationStatus = -1
    private var accelerometerCalibrationStatus = -1
    private var gyroscopeCalibrationStatus = -1

    private var isRunning = false
    private var currentMode = MODE_ROTATION_VECTOR
    private var lastUpdateTime = 0L

    /**
     * Longest gap the complementary filter will integrate across. Beyond it
     * the gyro contribution is meaningless and actively harmful — see the use
     * site. One second is far longer than any real inter-sample interval at
     * the rates this service registers.
     */
    private val MAX_FILTER_GAP_MS = 1_000L

    // Device orientation tracking
    /**
     * Which sign the image roll SHOULD have, from the gravity-based orientation class:
     * +1 for LANDSCAPE_RIGHT, -1 for LANDSCAPE_LEFT, 0 when the class does not say.
     *
     * This puts `deviceOrientation` back in the heading path, which the vector rewrite
     * took out — but for a different job. It is not remapping anything; it is breaking a
     * 180° tie, and it can do that because it comes from gravity rather than from the
     * fused attitude that is doing the flipping.
     */
    // SUPERSEDED 2026-10-10, kept beside the detector it feeds
    // (CameraPose.onWrongAttitudeBranchByOrientationClass) because the 729-capture
    // measurement behind the sign table is real. The branch test now asks gravity, which
    // has no "unknown" state to mistake for portrait — see that function for why.
    @Suppress("unused")
    /**
     * DOWN, as well as this device can say it: `TYPE_GRAVITY` when it has reported, the
     * raw accelerometer otherwise, and null before either has.
     *
     * `TYPE_GRAVITY` is itself gyro-fused, so it is smooth under hand movement in the way
     * a raw accelerometer sample is not — but it carries no magnetometer, which is the
     * whole point: it cannot be on the wrong branch of anything. The raw fallback exists
     * because the sensor is composite and an OEM may not offer it; it is noisier, and for
     * the binary branch test (a 90° margin) that does not matter at all.
     */
    private fun gravityVector(): FloatArray? = when {
        hasGravity -> gravityData
        hasAccelerometer -> accelerometerData
        else -> null
    }

    private fun expectedLandscapeRollSign(): Int =
        when (DeviceOrientation.toDegrees(deviceOrientation)) {
            270 -> 1
            90 -> -1
            else -> 0
        }

    /**
     * Whether this device is one that mirrors its azimuth — the pref the Armor-22
     * workaround has always used, read once per sample because it is a live toggle.
     */
    private val mirrorAzimuthWhenAffected: Boolean
        get() = context
            .getSharedPreferences("hillview_compass_prefs", Context.MODE_PRIVATE)
            .getBoolean("landscape_armor22_workaround", false)

    /** See the frame-probe in handleRotationVector — temporary, all four. */
    private var lastReversalProbeMs = 0L
    private var lastProbeBearing = Float.NaN
    private var gyroYawDeg = 0f
    private var lastGyroYawAtMs = 0L

    private var deviceOrientation = DeviceOrientation.PORTRAIT

    private val orientationEventListener = object : OrientationEventListener(context) {
        override fun onOrientationChanged(orientation: Int) {
			//Log.d(TAG, "📱 onOrientationChanged: $orientation")

            val newOrientation = DeviceOrientation.fromDegrees(orientation)

            if (newOrientation != deviceOrientation) {
                Log.d(TAG, "📱 Device orientation changed: $deviceOrientation → $newOrientation")
                deviceOrientation = newOrientation
                lastOrientationChangeElapsedMs = SystemClock.elapsedRealtime()
			}

        }
    }
    private var lastLocation: Location? = null

    // EMA smoothing state
    private var smoothedMagneticHeading: Float? = null
    private var smoothedTrueHeading: Float? = null
    private var smoothedPitch: Float? = null
    private var smoothedRoll: Float? = null
    private var lastSentMagneticHeading: Float? = null
    private var lastSentTrueHeading: Float? = null
    private var lastSentPitch: Float? = null
    private var lastSentRoll: Float? = null
    private var lastSentAccuracy: Int? = null

    // Rotation matrices
    private val rotationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)

    // Database storage for bearing history
    private val database = PhotoDatabase.getDatabase(context)
    private var lastDatabaseStorageTime = 0L
    private val databaseStorageIntervalMs = 100L // Store at most every 100ms (10 Hz)

    // Lifecycle and power management
    private var lifecycleObserver: AppLifecycleObserver? = null
    private var isPausedByLifecycle = false
    private var wasPausedBefore = false
    private var requestedMode = MODE_UPRIGHT_ROTATION_VECTOR

    init {
        // Initialize sensors
        rotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        gameRotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
        geomagneticRotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR)
        accelerometerSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        gyroscopeSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
        magnetometerSensor = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)

        headingSensor = sensorManager.getDefaultSensor(Sensor.TYPE_HEADING)
        poseSensor = sensorManager.getDefaultSensor(Sensor.TYPE_POSE_6DOF)



        // Log available sensors
        Log.i(TAG, "🔍 === ENHANCED SENSOR SERVICE INITIALIZED ===")
        Log.i(TAG, "🔍📱 Available sensors:")
        Log.i(TAG, "  ✓ TYPE_ROTATION_VECTOR: ${rotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GAME_ROTATION_VECTOR: ${gameRotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GEOMAGNETIC_ROTATION_VECTOR: ${geomagneticRotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_ACCELEROMETER: ${accelerometerSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GYROSCOPE: ${gyroscopeSensor != null}")
        Log.i(TAG, "  ✓ TYPE_MAGNETIC_FIELD: ${magnetometerSensor != null}")
        Log.i(TAG, "  ✓ TYPE_HEADING: ${headingSensor != null}")
        Log.i(TAG, "  ✓ TYPE_POSE_6DOF: ${poseSensor != null}")

        // Log sensor details if available
        gameRotationVectorSensor?.let {
            Log.i(TAG, "🔍📊 GAME_ROTATION_VECTOR details:")
            Log.i(TAG, "  - Name: ${it.name}")
            Log.i(TAG, "  - Vendor: ${it.vendor}")
            Log.i(TAG, "  - Max range: ${it.maximumRange}")
            Log.i(TAG, "  - Resolution: ${it.resolution}")
        }

        // Get last known location
        try {
            lastLocation = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                ?: locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
        } catch (e: SecurityException) {
            Log.w(TAG, "📍 Location permission not granted")
        }

        // Initialize lifecycle observer
        if (observeAppLifecycle) initializeLifecycleObserver()
    }

    /**
     * elapsedRealtime of the last RAW sensor event this listener received —
     * before rate limiting and before the change-suppression in
     * sendSensorData, so a phone lying perfectly still keeps this moving
     * while emitting nothing. The liveness signal an owner's watchdog needs:
     * a registered listener that has gone silent for seconds while the app
     * is in the foreground is stuck (seen after unbackgrounding), and the
     * only cure is a fresh registration. 0 until the first event.
     */
    @Volatile
    var lastRawEventElapsedMs: Long = 0L
        private set

    /**
     * When a raw attitude event last carried a DIFFERENT value from the one
     * before it — which is not the same question as when one last arrived.
     *
     * A rotation-vector sensor can go on delivering at full rate while
     * repeating one frozen sample (seen after unbackgrounding). Everything
     * downstream then looks alive: events flow, the EMA converges on the
     * frozen value, the elected bearing tracks it perfectly. The only
     * visible symptom is that the heading answers to nothing except the
     * device-orientation remap — which reads as "the compass alternates
     * between two values depending on how I hold the phone", because that
     * remap is then the only live input left in the chain.
     *
     * 0 until the first event.
     */
    @Volatile
    var lastRawValueChangeElapsedMs: Long = 0L
        private set

    /**
     * When the device-orientation class last changed. OrientationEventListener
     * registers its OWN accelerometer listener inside the framework, so this
     * keeps moving even when our registration is the dead one — which makes
     * it the evidence that the phone really moved while the attitude sample
     * did not. 0 until the first change.
     */
    @Volatile
    var lastOrientationChangeElapsedMs: Long = 0L
        private set

    /**
     * The device-orientation class the UPRIGHT remap is keyed on. Worth
     * showing to a person, because when the attitude sample freezes this is
     * the only live input left in the heading — so a readout that changes
     * ONLY when this changes is the signature of a frozen sensor.
     */
    val deviceOrientationName: String get() = deviceOrientation.name

    /** Whether a sensor registration is currently in place (not paused/stopped). */
    val running: Boolean get() = isRunning

    /**
     * Stop AND release the lifecycle observer / screen receiver. stopSensor()
     * alone is a PAUSE (the observer keeps the instance alive and resumes it
     * later); an owner that is done with the instance must call this, or
     * every instance it ever made stays registered with ProcessLifecycleOwner
     * and keeps re-registering its sensors on each foreground return.
     */
    fun destroy() {
        stopSensor()
        cleanupLifecycleObserver()
    }

    /**
     * Initialize the lifecycle observer for app foreground/background and screen on/off detection
     */
    private fun initializeLifecycleObserver() {
        lifecycleObserver = AppLifecycleObserver(context) { state ->
            handleAppStateChanged(state)
        }.also { observer ->
            observer.start()
            Log.i(TAG, "🔄 Lifecycle observer initialized and started")
        }
    }

    /**
     * Handle app state changes (foreground/background, screen on/off)
     */
    private fun handleAppStateChanged(state: AppLifecycleObserver.AppState) {
        Log.i(TAG, "🔄 App state changed: $state")

        if (state.shouldPauseSensors && isRunning && !isPausedByLifecycle) {
            Log.i(TAG, "⏸️ Pausing sensors due to app state")
            wasPausedBefore = true
            isPausedByLifecycle = true
            stopSensorInternal()
        } else if (!state.shouldPauseSensors && !isRunning && isPausedByLifecycle) {
            Log.i(TAG, "▶️ Resuming sensors due to app state")
            isPausedByLifecycle = false
            startSensorInternal(requestedMode)
        }
    }

    /**
     * Cleanup lifecycle observer
     */
    private fun cleanupLifecycleObserver() {
        lifecycleObserver?.let { observer ->
            observer.stop()
            Log.i(TAG, "🛑 Lifecycle observer stopped and cleaned up")
        }
        lifecycleObserver = null
    }

    fun startSensor(mode: Int = MODE_UPRIGHT_ROTATION_VECTOR) {
        requestedMode = mode
        if (!isPausedByLifecycle) {
            startSensorInternal(mode)
        } else {
            Log.i(TAG, "🔄 Sensor start requested but paused by lifecycle, will resume when app becomes active")
        }
    }

    /**
     * The single registration point — every mode's registerListener call goes
     * through here so [callbackHandler] cannot be forgotten by one branch.
     * The four-arg overload with a null handler is documented as equivalent to
     * the three-arg one (main looper), so the default path is unchanged.
     */
    private fun registerSensor(sensor: Sensor) {
        val ok = sensorManager.registerListener(this, sensor, sensorDelayUs, callbackHandler)
        // registerListener REFUSING is silent otherwise — and a refused
        // re-registration on foreground return is a compass that looks
        // healthy and never moves again.
        if (!ok) Log.w(TAG, "⚠️ registerListener refused for ${sensor.name} (type ${sensor.type})")
    }

    private fun startSensorInternal(mode: Int = MODE_UPRIGHT_ROTATION_VECTOR) {
        if (isRunning) {
            Log.w(TAG, "🔀 Sensor already running in mode: ${MODE_NAMES[currentMode]}, switching to ${MODE_NAMES[mode]}")
            stopSensorInternal()
        }

        // Boost the thread that PROCESSES sensor events, so a photo capture
        // cannot starve it.
        //
        // "The thread that processes them" used to mean "whoever called
        // this", which was right only by accident: with no callbackHandler
        // the events arrive on the main looper, and the caller is the main
        // thread too. frontend2 passes its own HandlerThread, so the boost
        // landed on the MAIN thread — pinning the UI thread at
        // URGENT_DISPLAY for the life of the process (nothing restores it)
        // while the thread it was meant for ran at default priority. An app
        // that holds its UI thread above the system's own display work is a
        // bad citizen on a weak device, and it was buying nothing.
        val boost = Runnable {
            try {
                if (originalThreadPriority == null) {
                    originalThreadPriority = Process.getThreadPriority(Process.myTid())
                }
                Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_DISPLAY)
                Log.i(TAG, "🚀 SENSOR THREAD PRIORITY: boosted from ${originalThreadPriority} to ${Process.THREAD_PRIORITY_URGENT_DISPLAY}")
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Failed to set sensor thread priority: ${e.message}")
            }
        }
        if (callbackHandler != null) callbackHandler.post(boost) else boost.run()

		Log.i(TAG, "🔍📡 TYPE_HEADING and TYPE_POSE_6DOF sensors if available: headingSensor: ${headingSensor != null}, poseSensor: ${poseSensor != null}")
        /*headingSensor?.let { registerSensor(it) }
        poseSensor?.let { registerSensor(it) }*/
		//isRunning = true

        currentMode = mode
        Log.i(TAG, "🔍🚀 Starting enhanced sensor service")
        Log.i(TAG, "🔍📋 Mode: ${MODE_NAMES[mode]} (code: $mode)")


        when (mode) {
            MODE_ROTATION_VECTOR -> {
                rotationVectorSensor?.let {
                    Log.d(TAG, "🔍📡 Registering TYPE_ROTATION_VECTOR sensor")
                    registerSensor(it)
                    isRunning = true
                    Log.i(TAG, "✅ Started TYPE_ROTATION_VECTOR successfully")
                } ?: Log.e(TAG, "❌ TYPE_ROTATION_VECTOR sensor not available")
            }
            MODE_GAME_ROTATION_VECTOR -> {
                // Try game rotation vector first (better for upright phone)
                gameRotationVectorSensor?.let {
                    Log.d(TAG, "🔍📡 Registering TYPE_GAME_ROTATION_VECTOR sensor")
                    Log.d(TAG, "🔍📱 This mode is optimized for upright phone usage")
                    registerSensor(it)
                    isRunning = true
                    Log.i(TAG, "✅ Started TYPE_GAME_ROTATION_VECTOR successfully")
                } ?: run {
                    // Fallback to regular rotation vector
                    Log.w(TAG, "⚠️ TYPE_GAME_ROTATION_VECTOR not available, falling back to ROTATION_VECTOR")
                    startSensor(MODE_ROTATION_VECTOR)
                }
            }
            MODE_MADGWICK_AHRS -> {
                // Register all raw sensors for Madgwick fusion
                Log.d(TAG, "🔍🔬 Setting up Madgwick AHRS sensor fusion")
                var sensorsRegistered = 0

                accelerometerSensor?.let {
                    registerSensor(it)
                    sensorsRegistered++
                    Log.d(TAG, "  ✓ Registered ACCELEROMETER")
                } ?: Log.w(TAG, "  ❌ ACCELEROMETER not available")

                gyroscopeSensor?.let {
                    registerSensor(it)
                    sensorsRegistered++
                    Log.d(TAG, "  ✓ Registered GYROSCOPE")
                } ?: Log.w(TAG, "  ❌ GYROSCOPE not available")

                magnetometerSensor?.let {
                    registerSensor(it)
                    sensorsRegistered++
                    Log.d(TAG, "  ✓ Registered MAGNETOMETER")
                } ?: Log.w(TAG, "  ❌ MAGNETOMETER not available")

                if (sensorsRegistered == 3) {
                    madgwickAHRS.reset()
                    isRunning = true
                    Log.i(TAG, "✅ Started Madgwick AHRS with all 3 sensors")
                } else {
                    Log.e(TAG, "❌ Madgwick AHRS requires all 3 sensors, only $sensorsRegistered available")
                    stopSensor()
                }
            }
            MODE_COMPLEMENTARY_FILTER -> {
                // Use accelerometer + magnetometer with complementary filter
                accelerometerSensor?.let {
                    registerSensor(it)
                }
                magnetometerSensor?.let {
                    registerSensor(it)
                }
                gyroscopeSensor?.let {
                    registerSensor(it)
                }
                isRunning = true
                Log.i(TAG, "Started complementary filter")
            }
            MODE_UPRIGHT_ROTATION_VECTOR -> {
                // Use rotation vector but optimized for upright phone position
                magnetometerSensor?.let {
                    registerSensor(it)
                    Log.d(TAG, "  ✓ Registered MAGNETOMETER")
                } ?: Log.w(TAG, "  ❌ MAGNETOMETER not available")

                // FOR THE FRAME PROBE, and this mode did not use it before. The
                // gyroscope measures the true angular rate whatever the fusion believes,
                // so it is the one reference that can say which of the two is wrong when
                // the fused heading turns the wrong way. Cheap here: during capture the
                // IMU window already runs this sensor at SENSOR_DELAY_FASTEST, so the
                // hardware is on and the HAL multiplexes another listener for nearly
                // nothing. Remove with the probe.
                gyroscopeSensor?.let {
                    registerSensor(it)
                    Log.d(TAG, "  ✓ Registered GYROSCOPE (frame probe)")
                }

                // THE INDEPENDENT REFERENCE FOR THE 180° BRANCH TEST, and this mode did
                // not register it before. Gravity is a different stream from the fused
                // rotation vector, so it is the one thing that can say the fused
                // attitude is on the wrong branch — see CameraPose.onWrongAttitudeBranch
                // for why the gravity-based ORIENTATION CLASS could not do that job.
                // Cheap for the same reason as the gyroscope above: during capture the
                // IMU window already runs this sensor, so the hardware is on.
                accelerometerSensor?.let {
                    registerSensor(it)
                    Log.d(TAG, "  ✓ Registered ACCELEROMETER (branch reference)")
                } ?: Log.w(TAG, "  ❌ ACCELEROMETER not available — branch test declines")

                // DOWN, gyro-stabilised and with no magnetometer in it — the source of
                // the published pitch and roll since 2026-10-10, and the reference the
                // branch test compares the fused matrix against. Composite, so it may be
                // absent; gravityVector() falls back to the raw accelerometer.
                sensorManager.getDefaultSensor(Sensor.TYPE_GRAVITY)?.let {
                    registerSensor(it)
                    Log.d(TAG, "  ✓ Registered GRAVITY")
                } ?: Log.i(TAG, "  no TYPE_GRAVITY — falling back to the raw accelerometer")

                rotationVectorSensor?.let {
                    Log.d(TAG, "🔄 Registering TYPE_ROTATION_VECTOR sensor for UPRIGHT mode")
                    registerSensor(it)
                    isRunning = true
                } ?: run {
                    Log.e(TAG, "❌ TYPE_ROTATION_VECTOR not available")
                }
            }
        }

        if (!isRunning) {
            Log.e(TAG, "❌ Failed to start any sensor mode")
        } else {
            // Start orientation listener for device orientation tracking
            if (orientationEventListener.canDetectOrientation()) {
                orientationEventListener.enable()
                Log.d(TAG, "📱 Enabled device orientation tracking")
            } else {
                Log.w(TAG, "📱 Device orientation detection not supported")
            }

            Log.i(TAG, "🔍🎯 Current configuration:")
            Log.i(TAG, "  - Mode: ${MODE_NAMES[currentMode]}")
            Log.i(TAG, "  - Rate limit: ${MODE_RATE_LIMITS[currentMode]}ms (${1000.0/(MODE_RATE_LIMITS[currentMode]?:100)} Hz)")
            Log.i(TAG, "  - Sensor delay: ${sensorDelayUs / 1000}ms")
        }
    }

    private fun stopSensorInternal() {
        stopSensor()
    }

    fun stopSensor() {
        if (isRunning) {
            Log.i(TAG, "🔍🛑 Stopping sensor service (mode: ${MODE_NAMES[currentMode]})")
            sensorManager.unregisterListener(this)

            // Stop orientation listener
            orientationEventListener.disable()
            Log.d(TAG, "📱 Disabled device orientation tracking")

            isRunning = false
            hasAccelerometer = false
            hasGyroscope = false
            hasMagnetometer = false

            // Reset smoothing state to avoid stale values on restart
            lastUpdateTime = 0L
            lastComplementaryUpdate = 0L
            smoothedMagneticHeading = null
            smoothedTrueHeading = null
            smoothedPitch = null
            smoothedRoll = null
            lastSentMagneticHeading = null
            lastSentTrueHeading = null
            lastSentPitch = null
            lastSentRoll = null
            lastSentAccuracy = null

            Log.i(TAG, "✅ Sensor service stopped successfully (smoothing state reset)")
        } else {
            Log.w(TAG, "⚠️ Sensor service already stopped")
        }
    }

    fun updateLocation(latitude: Double, longitude: Double) {
        lastLocation = Location(LocationManager.GPS_PROVIDER).apply {
            this.latitude = latitude
            this.longitude = longitude
        }
        //Log.d(TAG, "📍 Updated location: $latitude, $longitude")
    }

    private fun accuracyToString(accuracy: Int): String {
        return when (accuracy) {
            SensorManager.SENSOR_STATUS_ACCURACY_HIGH -> "HIGH"
            SensorManager.SENSOR_STATUS_ACCURACY_MEDIUM -> "MEDIUM"
            SensorManager.SENSOR_STATUS_ACCURACY_LOW -> "LOW"
            SensorManager.SENSOR_STATUS_UNRELIABLE -> "UNRELIABLE"
            else -> "UNKNOWN"
        }
    }


	fun logEvent(event: SensorEvent) {
	    //Log.d(TAG, "SensorEvent type=${event.sensor.type}, values=${event.values.joinToString()}")


		if (event.sensor.type == Sensor.TYPE_HEADING) {
			/*
			Sensor.TYPE_HEADING:
			A sensor of this type measures the direction in which the device is pointing relative to true north in degrees. The value must be between 0.0 (inclusive) and 360.0 (exclusive), with 0 indicating north, 90 east, 180 south, and 270 west. Accuracy is defined at 68% confidence. In the case where the underlying distribution is assumed Gaussian normal, this would be considered one standard deviation. For example, if heading returns 60 degrees, and accuracy returns 10 degrees, then there is a 68 percent probability of the true heading being between 50 degrees and 70 degrees.

				values[0]: Measured heading in degrees.
				values[1]: Heading accuracy in degrees.
			*/

			val heading = event.values[0]
			val accuracy = event.values[1]

			Log.d(TAG, "🔍🧭TYPE_HEADING data: heading=${heading.format(1)}°, accuracy=±${accuracy.format(1)}°")

		}
		else if (event.sensor.type == Sensor.TYPE_POSE_6DOF) {
			/*
				A TYPE_POSE_6DOF event consists of a rotation expressed as a quaternion and a translation expressed in SI units. The event also contains a delta rotation and translation that show how the device?s pose has changed since the previous sequence numbered pose. The event uses the cannonical Android Sensor axes.

				values[0]: x*sin(θ/2)
				values[1]: y*sin(θ/2)
				values[2]: z*sin(θ/2)
				values[3]: cos(θ/2)
				values[4]: Translation along x axis from an arbitrary origin.
				values[5]: Translation along y axis from an arbitrary origin.
				values[6]: Translation along z axis from an arbitrary origin.
				values[7]: Delta quaternion rotation x*sin(θ/2)
				values[8]: Delta quaternion rotation y*sin(θ/2)
				values[9]: Delta quaternion rotation z*sin(θ/2)
				values[10]: Delta quaternion rotation cos(θ/2)
				values[11]: Delta translation along x axis.
				values[12]: Delta translation along y axis.
				values[13]: Delta translation along z axis.
				values[14]: Sequence number
			*/

			val qx = event.values[0]
			val qy = event.values[1]
			val qz = event.values[2]
			val qw = event.values[3]
			val tx = event.values[4]
			val ty = event.values[5]
			val tz = event.values[6]
			Log.d(TAG, "🔍🤖TYPE_POSE_6DOF data: quaternion=[$qx, $qy, $qz, $qw], translation=[$tx, $ty, $tz]")

		}

	}

    private var lastRawVectorValues: FloatArray? = null

    override fun onSensorChanged(event: SensorEvent) {
        lastRawEventElapsedMs = SystemClock.elapsedRealtime()

        // Exact comparison, deliberately: a live sensor's last decimal
        // always jitters, so bit-identical samples mean a repeated one, not
        // a still phone. (And a still phone is not harmed by being noticed
        // — the stuck check upstream also demands evidence of movement.)
        if (event.sensor.type == Sensor.TYPE_ROTATION_VECTOR ||
            event.sensor.type == Sensor.TYPE_GAME_ROTATION_VECTOR ||
            event.sensor.type == Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR
        ) {
            val previous = lastRawVectorValues
            if (previous == null || !previous.contentEquals(event.values)) {
                lastRawValueChangeElapsedMs = lastRawEventElapsedMs
                lastRawVectorValues = event.values.clone()
            }
        }

		logEvent(event)


        when (event.sensor.type) {
            Sensor.TYPE_ROTATION_VECTOR -> {
                //Log.v(TAG, "🔍📡 Received TYPE_ROTATION_VECTOR data")
                handleRotationVector(event, "TYPE_ROTATION_VECTOR")
            }
            /*Sensor.TYPE_GAME_ROTATION_VECTOR -> {
                Log.v(TAG, "🔍🎮 Received TYPE_GAME_ROTATION_VECTOR data")
                handleRotationVector(event, "TYPE_GAME_ROTATION_VECTOR")
            }
            Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR -> {
                Log.v(TAG, "🔍🧭 Received TYPE_GEOMAGNETIC_ROTATION_VECTOR data")
                handleRotationVector(event, "TYPE_GEOMAGNETIC_ROTATION_VECTOR")
            }
            Sensor.TYPE_GRAVITY -> {
                gravityData = event.values.clone()
                hasGravity = true
            }
            Sensor.TYPE_ACCELEROMETER -> {
                accelerometerData = event.values.clone()
                hasAccelerometer = true
                if (currentMode == MODE_MADGWICK_AHRS) {
                    updateMadgwick()
                } else if (currentMode == MODE_COMPLEMENTARY_FILTER) {
                    updateComplementaryFilter()
                }
            }
            Sensor.TYPE_GYROSCOPE -> {
                gyroscopeData = event.values.clone()
                hasGyroscope = true
                if (currentMode == MODE_MADGWICK_AHRS) {
                    updateMadgwick()
                } else if (currentMode == MODE_COMPLEMENTARY_FILTER) {
                    updateComplementaryFilter()
                }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                magnetometerData = event.values.clone()
                hasMagnetometer = true
                if (currentMode == MODE_MADGWICK_AHRS) {
                    updateMadgwick()
                } else if (currentMode == MODE_COMPLEMENTARY_FILTER) {
                    updateComplementaryFilter()
                }
            }*/
        }
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {
        val accuracyStr = accuracyToString(accuracy)

		Log.i(TAG, "🔍📐 Sensor accuracy changed: ${sensor.name} (type: ${sensor.type}) → $accuracyStr ($accuracy)")

        when (sensor.type) {
            Sensor.TYPE_MAGNETIC_FIELD -> {
                magnetometerCalibrationStatus = accuracy
                Log.i(TAG, "🔍🧭 Magnetometer accuracy changed: $accuracyStr ($accuracy)")
                if (accuracy == SensorManager.SENSOR_STATUS_ACCURACY_LOW) {
                    Log.w(TAG, "⚠️ Low magnetometer accuracy - consider calibrating by moving device in figure-8 pattern")
                }
            }
            Sensor.TYPE_ACCELEROMETER -> {
                accelerometerCalibrationStatus = accuracy
                Log.d(TAG, "🔍📈 Accelerometer accuracy: $accuracyStr")
            }
            Sensor.TYPE_GYROSCOPE -> {
                gyroscopeCalibrationStatus = accuracy
                Log.d(TAG, "🔍🔄 Gyroscope accuracy: $accuracyStr")
            }
        }
    }


    private fun handleRotationVector(event: SensorEvent, source: String) {
        // Rate limiting based on current mode. MONOTONIC: this is an
        // elapsed-time decision, and the wall clock can step BACKWARD (an NTP
        // correction on resume, the user setting the time). When it did, this
        // subtraction went negative and stayed under the limit until wall time
        // climbed back past lastUpdateTime — dropping every sample for the
        // length of the jump, which is a compass frozen at its last heading
        // while the sensors are perfectly healthy.
        val currentTime = SystemClock.elapsedRealtime()
        val rateLimit = MODE_RATE_LIMITS[currentMode] ?: UPDATE_RATE_MS

        // DECIDE, do not return. The cap belongs to what it was written for — the
        // compass needle and the bearings rows — but returning here also denied the
        // orientation maths to the capture's at-exposure lookup, which wants every
        // sample. The maths is a rotation matrix, a remap and a getOrientation: at
        // 33 Hz its cost is not worth a capped pose.
        //
        // Only this handler. The Madgwick and complementary paths derive their filter
        // `dt` from this same clock, so the limit is part of their dynamics there; they
        // keep it, and neither is the mode in use (TYPE_ROTATION_VECTOR / UPRIGHT).
        val publish = currentTime - lastUpdateTime >= rateLimit
        if (publish) lastUpdateTime = currentTime

        //Log.v(TAG, "🔍📊 Processing $source data")

        // Get rotation matrix
        SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)

        // WHERE THE LENS POINTS, by transforming the camera axis — NOT by reading Euler
        // angles out of a remapped frame. The matrix is deliberately left un-remapped:
        // a vector transform has no quantized orientation class to key on, which is the
        // entire point. See CameraPose for the measurements that retired the old path
        // and [legacyOrientationFromRemappedMatrix] for what it did.
        val rawLens = cameraPoseFromRotationMatrix(rotationMatrix)
        // THE DEVICE QUIRK, applied where it was measured and nowhere else. The pref is
        // the one the Armor-22 workaround already used; what changed is the KEY. The old
        // code negated past 90° of roll and also added 180° unconditionally; the pair
        // happened to come out right in a level landscape hold and wrong elsewhere. See
        // CameraPose.inMirroredAzimuthRegion for the two datasets that settled it.
        // TWO corrections, in the order the original applied them — the branch fix first,
        // then the device mirror. The order happens NOT to matter: the two commute,
        // because -(a+180) and -a+180 are the same angle. Kept in the original's order
        // anyway, since matching it costs nothing and makes the two readable side by
        // side; a test pins the commutation so nobody has to re-derive it.
        //
        // What is different from the original is that they are now keyed INDEPENDENTLY.
        // There both hung off `abs(roll) > 90`, which in that convention happened to
        // mean "landscape" and "wrong branch" at once. Here the branch fix keys on the
        // roll's SIGN against the gravity-based orientation class, and the mirror on
        // landscape-plus-lens-above-horizon, because the measurements say those are two
        // different conditions.
        //
        // Both decisions are HOISTED into named flags because they are stamped onto the
        // photo (OrientationSensorData.branchCorrected / azimuthMirrored). Re-deriving
        // afterwards from the roll sign is exactly the archaeology that cost two
        // sessions here: by the time a heading reaches an upload, a corrected sample and
        // one that never needed correcting look identical.
        // GRAVITY decides, not the quantized orientation class. The class reports
        // ORIENTATION_UNKNOWN as FLAT_UP as 0, which is also PORTRAIT, so pitched down it
        // flickered this correction on and off and the reported roll jumped 180° and back
        // while the phone moved smoothly (user, 2026-10-10: rotating portrait → landscape
        // below the horizon read 0, −10, … +110, +90 — which is −70+180, −80+180,
        // −90+180). Gravity has no unknown state and no buckets.
        val down = gravityVector()
        val gravityConditioning = down?.let {
            gravityRollConditioning(it[0], it[1], it[2])
        } ?: 0f
        val gravityRoll = if (down != null && gravityConditioning >= GRAVITY_ROLL_FLOOR) {
            gravityRollDeg(down[0], down[1])
        } else {
            null
        }
        val onWrongBranch = rawLens != null &&
            rawLens.onWrongAttitudeBranch(gravityRoll, gravityConditioning)
        val branched = if (rawLens != null && onWrongBranch) {
            rawLens.withBranchCorrected()
        } else {
            rawLens
        }
        val mirrorAzimuth = branched != null && mirrorAzimuthWhenAffected &&
            branched.inMirroredAzimuthRegion()
        val lens = if (branched != null && mirrorAzimuth) {
            branched.withMirroredAzimuth()
        } else {
            branched
        }
        if (lens == null) {
            // All zeros until the first usable sample. Publishing would assert a level
            // camera facing due north, which is a plausible lie rather than an absence.
            Log.v(TAG, "🔍📐 no usable rotation matrix yet from $source")
            return
        }
        // THE POINTING bearing, not the bare camera one: with the phone flat on a table
        // the lens points at the table and only the top edge has a horizontal direction
        // left. The old getOrientation path published the top edge and so kept working
        // on a desk — losing that was a real regression (user, 2026-10-09: "good for
        // using the map with phone on a table"). See CameraPose.pointingBearingDeg; the
        // camera still dominates wherever the lens is off vertical, so nothing about
        // shooting changes.
        val heading = lens.pointingBearingDeg
        // PITCH AND ROLL FROM GRAVITY, not from the fused matrix. They never needed the
        // magnetometer: there is exactly one down, and it fixes the optical axis's tilt
        // and the image's rotation about it completely. The fused matrix needs the
        // magnetometer because it also has to answer WHICH WAY IS NORTH, and resolving
        // that is what forces a choice between the two attitudes that fit the readings —
        // the 180° branch. So the branch ambiguity is the heading's problem, and letting
        // it reach the roll was giving away two good axes to buy one doubtful one.
        //
        // Measured on 94 prod captures where the matrix is on the right branch: the two
        // rolls differ by a mean of -0.95° (sd 3.33) and the two pitches by -0.29°
        // (sd 1.32), so there is no systematic disagreement to lose — a few degrees of
        // scatter against an entire class of 180° failure. The user saw it first:
        // "g matches closely what i would call an intuitive understanding of the phone's
        // roll axis values" (2026-10-10).
        //
        // The matrix keeps the bearing, and keeps BOTH correction decisions, which still
        // compare it against gravity. What changes is only which number is published.
        val pitch = down?.let { gravityPitchDeg(it[0], it[1], it[2]) } ?: lens.pitchDeg
        // Roll needs gravity's IN-PLANE direction, which does not exist with the phone
        // flat — the rotation about a vertical optical axis is an azimuth, and gravity
        // cannot see azimuths. There the fused matrix answers, exactly as the bearing
        // falls back to the device's top edge when the lens goes vertical.
        val roll = if (gravityRoll != null) gravityRoll else lens.imageRollDeg

        // THE INDEPENDENT REFERENCE. World up in device coordinates is the matrix's
        // third row, so the gyro's component along it is the true yaw rate — positive is
        // counter-clockwise about up, which is a DECREASING compass bearing, hence the
        // negation. Integrated across every sample between probe emissions so it can be
        // compared with what the fused heading did over the same interval.
        //
        // Opposite signs mean the fusion is turning the wrong way, and the gyroscope
        // says so without any procedure from whoever is holding the phone — which is the
        // point, because two structural explanations have already been wrong and the
        // boundary is what needs measuring rather than guessing.
        gyroscopeData?.let { g ->
            val yawRate = g[0] * rotationMatrix[6] + g[1] * rotationMatrix[7] +
                g[2] * rotationMatrix[8]
            val dtMs = (currentTime - lastGyroYawAtMs).coerceIn(0L, 200L)
            if (lastGyroYawAtMs != 0L) {
                gyroYawDeg += -Math.toDegrees(yawRate.toDouble()).toFloat() * dtMs / 1000f
            }
            lastGyroYawAtMs = currentTime
        }
        if (!lens.bearingIsDefined()) {
            // Within ~3° of straight up or down, where a bearing does not EXIST — the
            // horizontal projection it comes from has almost no length. The pose is
            // still published, because pitch and roll are perfectly well defined there;
            // this line is so the condition has a name in the log rather than appearing
            // as a compass that went wild.
            Log.d(
                TAG,
                "🔍🧭 lens within ${"%.1f".format(90f - abs(pitch))}° of vertical — " +
                    "bearing from ${lens.bearingReference} (camera horizontal " +
                    "${lens.horizontalLength}, top edge ${lens.deviceHorizontalLength})",
            )
        }

        // TEMPORARY, TARGETED DIAGNOSTIC. A bearing reversal was reported that is
        // confined to landscape with the lens above the horizon — and nothing between
        // the matrix and `heading` is conditional on either, so the matrix itself is the
        // only place it can come from. This records exactly that posture and nothing
        // else, into the Event log, where it can be copied off a phone with no cable.
        //
        // `det` is the question: +1 says the HAL handed us a proper rotation and the
        // reversal is a rotation pointing the wrong way; −1 says it handed us a MIRRORED
        // frame, which is what a negation genuinely compensates and would vindicate the
        // Armor-22 hack as fixing a real device defect. The lens vector is there so the
        // reversal can be watched directly in world coordinates while the phone turns.
        //
        // Delete this once the question is answered.
        // WIDENED to every posture, 2026-10-10. The landscape sweep showed all three
        // device axes yawing -405° while the phone turned +405° clockwise, with
        // det(R) = +1 throughout — so the matrix is a proper rotation that reports the
        // HEADING mirrored, and no choice of axis can undo that. A world frame with East
        // negated explains every observation at once: the up component is untouched (so
        // pitch still matches gravity), world-up in device coords is untouched (so the
        // image roll is fine), and only the bearing reverses.
        //
        // If that is right it is GLOBAL, so portrait must reverse too — and portrait is
        // reported as working. One sweep in portrait settles which, so the posture gate
        // is gone and the roll is logged for segmenting afterwards.
        if (currentTime - lastReversalProbeMs > REVERSAL_PROBE_PERIOD_MS) {
            // What the fused heading DID against what the gyroscope says it should
            // have: agreeing signs mean the fusion is sound in this posture, opposite
            // signs are the reversal — per posture, per sample, no procedure.
            val fusedDelta = if (lastProbeBearing.isNaN()) 0f
                else signedDegreeDelta(lastProbeBearing, heading)
            val verdict = when {
                lastProbeBearing.isNaN() || abs(gyroYawDeg) < 5f -> "idle"
                fusedDelta * gyroYawDeg < 0f -> "REVERSED"
                else -> "agrees"
            }
            lastProbeBearing = heading
            lastReversalProbeMs = currentTime
            EventLog.record(
                "frame-probe",
                "$verdict fused ${"%+.1f".format(fusedDelta)} gyro " +
                    "${"%+.1f".format(gyroYawDeg)} · " +
                    "bearing ${"%.1f".format(heading)} pitch ${"%.1f".format(pitch)} " +
                    "roll ${"%.1f".format(roll)} det ${"%.4f".format(lens.determinant)} " +
                    "lens e/n/u ${"%.3f".format(lens.lensEast)}/" +
                    "${"%.3f".format(lens.lensNorth)}/${"%.3f".format(lens.lensUp)} " +
                    "rv ${event.values.take(4).joinToString(",") { "%.4f".format(it) }}",
            )
            gyroYawDeg = 0f
        }

        // Apply magnetic declination to convert from magnetic north to true north
        val declination = getMagneticDeclination()
        val trueHeading = (heading + declination + 360) % 360

        // Log every 20th update to avoid spam
        /*if (Math.random() < 0.05) {
            Log.d(TAG, "🔍🧭 $source bearing:")
            Log.d(TAG, "  - Magnetic: ${heading.format(1)}°")
            Log.d(TAG, "  - True: ${trueHeading.format(1)}°")*/
            //Log.d(TAG, "  - Accuracy level: ${event.accuracy}")
            /*
            Log.d(TAG, "  - Pitch: ${pitch.format(1)}°, Roll: ${roll.format(1)}°")
        }*/

        // Include mode information in source
        val sourceWithMode = when (currentMode) {
            // "(UPRIGHT MODE)" until 2026-10-10, naming a remap by orientation class
            // that no longer exists — the angles come from transforming the camera axis
            // now. The label has to change with the maths, or every row uploaded from
            // here on claims a provenance that was retired.
            MODE_UPRIGHT_ROTATION_VECTOR -> "$source (camera-axis)"
            MODE_MADGWICK_AHRS -> "$source MADGWICK_AHRS"
            MODE_COMPLEMENTARY_FILTER -> "$source COMPLEMENTARY_FILTER"
            else -> source
        }

        sendSensorData(
            magneticHeading = heading,
            trueHeading = trueHeading,
            accuracyLevel = magnetometerCalibrationStatus,
            pitch = pitch,
            roll = roll,
            source = sourceWithMode,
            publish = publish,
            // The rotation-vector sample rates itself; this is the one path
            // where a real value exists to pass on.
            fusedSensorAccuracy = event.accuracy,
            // What the HAL said and what we made of it, kept separable on the frame.
            pose = lens,
            rotationVector = event.values,
            branchCorrected = onWrongBranch,
            azimuthMirrored = mirrorAzimuth,
        )
    }



    /**
     * Applies coordinate system remapping based on device orientation for accurate heading calculation.
     * This function is pure and testable - it takes orientation and rotation matrix as inputs
     * and returns the remapped matrix without side effects.
     *
     * @param rotationMatrix Input rotation matrix from sensor
     * @param orientation Device orientation enum
     * @return Remapped rotation matrix appropriate for the given orientation
     */
    @Suppress("REDUNDANT_ELSE_IN_WHEN") // see the `else` below: deliberate, not forgotten
    private fun remapCoordinatesForOrientation(rotationMatrix: FloatArray, orientation: DeviceOrientation): FloatArray {
        val remappedMatrix = FloatArray(9)

        when (orientation) {
			DeviceOrientation.FLAT_UP, DeviceOrientation.FLAT_DOWN -> {
				// No remapping needed for flat orientations
				//Log.v(TAG, "🔄 No remapping needed for FLAT_UP or FLAT_DOWN orientation")
				System.arraycopy(rotationMatrix, 0, remappedMatrix, 0, 9)
			}
            DeviceOrientation.PORTRAIT -> {
                // Default portrait orientation - phone held upright
                // Remap X axis to Z axis, Y axis stays Y
                SensorManager.remapCoordinateSystem(
                    rotationMatrix,
                    SensorManager.AXIS_X,
                    SensorManager.AXIS_Z,
                    remappedMatrix
                )
				//Log.v(TAG, "🔄 Remappingrrrr for PORTRAIT orientation")
            }
            DeviceOrientation.LANDSCAPE_RIGHT -> {
                // Phone rotated 90° counter-clockwise (landscape, home button on right)
                // Remap coordinates: Y→X, -X→Y for proper heading calculation
                SensorManager.remapCoordinateSystem(
                    rotationMatrix,
                    SensorManager.AXIS_Y,
                    SensorManager.AXIS_MINUS_X,
                    remappedMatrix
                )
				//Log.v(TAG, "🔄 Remappingrrrr for LANDSCAPE_LEFT orientation")
            }
            DeviceOrientation.LANDSCAPE_LEFT -> {
                // Phone rotated 90° clockwise (landscape, home button on left)
                // Remap coordinates: -Y→X, X→Y for proper heading calculation
                SensorManager.remapCoordinateSystem(
                    rotationMatrix,
                    SensorManager.AXIS_MINUS_Y,
                    SensorManager.AXIS_X,
                    remappedMatrix
                )
				//Log.v(TAG, "🔄 Remappingrrrr for LANDSCAPE_RIGHT orientation")
            }
            DeviceOrientation.PORTRAIT_INVERTED -> {
                // Phone upside down (180° rotation)
                // Remap coordinates: -X→Z, -Z→Y for proper heading calculation
                SensorManager.remapCoordinateSystem(
                    rotationMatrix,
                    SensorManager.AXIS_MINUS_X,
                    SensorManager.AXIS_MINUS_Z,
                    remappedMatrix
                )
				//Log.v(TAG, "🔄 Remappingrrrr for PORTRAIT_INVERTED orientation")
            }
			else -> {
				Log.w(TAG, "⚠️ Unknown device orientation, no remapping applied")
				System.arraycopy(rotationMatrix, 0, remappedMatrix, 0, 9)
			}
        }

        return remappedMatrix
    }

    /**
     * THE PATH THAT WAS REPLACED on 2026-10-08, kept because it is the record of what
     * the old numbers meant — every row captured before that build came out of this, and
     * recovering one needs to know exactly what it did. Nothing calls it.
     *
     * It remapped the rotation matrix by a QUANTIZED orientation class and then read
     * Euler angles out of the result, patching them with two step functions keyed on
     * `roll` — one of which carried the comment `// magic`, which is the honest label for
     * a sign fix applied to a frame that was already wrong.
     *
     * Why it had to go, measured against gravity on real captures (2026-10-03):
     *  - the portrait remap sends device Y to world Z (up) — the "phone is upright"
     *    part — while NEITHER landscape remap sends anything to Z. So in landscape the
     *    frame has no axis near world up, `getOrientation`'s pitch pins near ∓90 and its
     *    roll goes ill-conditioned: one up/level/down sweep published −56.7 / −84.4 /
     *    −68.0 where gravity said −33.7 / −4.4 / +21.8, and `roll` flipped −176.8 → +2.7
     *    between consecutive frames — flipping the two corrections below on and off,
     *    because they are keyed on exactly that degenerate value;
     *  - the orientation classifier only calls it landscape from 45°, so at 38° of roll
     *    the PORTRAIT remap was applied to a rolled phone. Three deliberate ~40°
     *    captures landed 43–52° off their own un-rolled neighbours.
     *
     * The replacement is proven in `CameraPoseTest`, which builds matrices from named
     * device axes — the opposite direction from the code — so a sign error cannot cancel.
     */
    @Suppress("unused")
    private fun legacyOrientationFromRemappedMatrix(event: SensorEvent, source: String): Triple<Float, Float, Float> {
        SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)
        // Apply coordinate remapping based on device orientation
        if (currentMode == MODE_UPRIGHT_ROTATION_VECTOR) {
            val remappedMatrix = remapCoordinatesForOrientation(rotationMatrix, deviceOrientation)
            System.arraycopy(remappedMatrix, 0, rotationMatrix, 0, 9)
            //Log.v(TAG, "🔄 Applied coordinate remapping for ${deviceOrientation}")
        }
		else
		{
			Log.v(TAG, "🔄 No coordinate remapping applied for mode: ${MODE_NAMES[currentMode]}")
		}

        // Get orientation
        SensorManager.getOrientation(rotationMatrix, orientation)

        // Convert to degrees
        var azimuth = (Math.toDegrees(orientation[0].toDouble()).toFloat() + 360) % 360
        val pitch = Math.toDegrees(orientation[1].toDouble()).toFloat()
        val roll = Math.toDegrees(orientation[2].toDouble()).toFloat()


		if (abs(roll) > 90) {
			azimuth += 180
		}
		val prefs = context.getSharedPreferences("hillview_compass_prefs", Context.MODE_PRIVATE)
        val workaround1 = prefs.getBoolean("landscape_armor22_workaround", false)
		if (workaround1) {
			if (abs(roll) > 90) {
				azimuth = 0 - azimuth // magic
			}
		}
		azimuth = (azimuth + 360*2) % 360

		//Log.v(TAG, "🔍📊 $source orientation: azimuth=${azimuth.format(1)}°, pitch=${pitch.format(1)}°, roll=${roll.format(1)}°, accuracy=${event.accuracy}, orientation=${deviceOrientation}")

        // Normalize heading
        val heading = if (azimuth < 0) azimuth + 360 else azimuth

        // Apply magnetic declination to convert from magnetic north to true north
        val declination = getMagneticDeclination()
        return Triple(heading, pitch, roll)
    }




    private fun updateMadgwick() {
        if (!hasAccelerometer || !hasGyroscope || !hasMagnetometer) {
            return
        }

        // Rate limiting — monotonic, see handleRotationVector.
        val currentTime = SystemClock.elapsedRealtime()
        val rateLimit = MODE_RATE_LIMITS[currentMode] ?: UPDATE_RATE_MS

        if (currentTime - lastUpdateTime < rateLimit) {
            return
        }
        lastUpdateTime = currentTime

        Log.v(TAG, "🔍🔬 Madgwick AHRS update")

        // Update Madgwick filter
        madgwickAHRS.update(
            gyroscopeData[0], gyroscopeData[1], gyroscopeData[2],
            accelerometerData[0], accelerometerData[1], accelerometerData[2],
            magnetometerData[0], magnetometerData[1], magnetometerData[2]
        )

        // Log raw sensor values occasionally
        if (Math.random() < 0.02) {
            Log.v(TAG, "  Raw sensor values:")
            Log.v(TAG, "  - Gyro: [${gyroscopeData[0].format(3)}, ${gyroscopeData[1].format(3)}, ${gyroscopeData[2].format(3)}] rad/s")
            Log.v(TAG, "  - Accel: [${accelerometerData[0].format(2)}, ${accelerometerData[1].format(2)}, ${accelerometerData[2].format(2)}] m/s²")
            Log.v(TAG, "  - Mag: [${magnetometerData[0].format(1)}, ${magnetometerData[1].format(1)}, ${magnetometerData[2].format(1)}] μT")
        }

        // Get Euler angles
        val (yaw, pitch, roll) = madgwickAHRS.getEulerAngles()

        // Convert to degrees and negate yaw for correct compass direction
        // (clockwise rotation should increase heading)
        val heading = -Math.toDegrees(yaw.toDouble()).toFloat()
        val pitchDeg = Math.toDegrees(pitch.toDouble()).toFloat()
        val rollDeg = Math.toDegrees(roll.toDouble()).toFloat()

        // Normalize and apply declination
        val normalizedHeading = if (heading < 0) heading + 360 else heading
        val declination = getMagneticDeclination()
        val trueHeading = (normalizedHeading + declination + 360) % 360

        // Log Madgwick output occasionally
        if (Math.random() < 0.05) {
            Log.d(TAG, "🔍🔬 Madgwick AHRS output:")
            Log.d(TAG, "  - Yaw/Heading: ${normalizedHeading.format(1)}°")
            Log.d(TAG, "  - Pitch: ${pitchDeg.format(1)}°")
            Log.d(TAG, "  - Roll: ${rollDeg.format(1)}°")
            Log.d(TAG, "  - Declination: ${declination.format(1)}°")
        }

        sendSensorData(
            magneticHeading = normalizedHeading,
            trueHeading = trueHeading,
            accuracyLevel = magnetometerCalibrationStatus,
            pitch = pitchDeg,
            roll = rollDeg,
            source = "Madgwick_AHRS"
        )
    }

    private fun updateComplementaryFilter() {
        if (!hasAccelerometer || !hasMagnetometer) {
            return
        }

        // Monotonic, see handleRotationVector — and doubly so here: `dt` for
        // the complementary filter below is derived from this, and a backward
        // step would feed the filter a negative interval.
        val currentTime = SystemClock.elapsedRealtime()
        val rateLimit = MODE_RATE_LIMITS[currentMode] ?: UPDATE_RATE_MS

        if (currentTime - lastUpdateTime < rateLimit) {
            return
        }

        Log.v(TAG, "🔍🔄 Complementary filter update")

        // Calculate orientation from accelerometer and magnetometer
        if (SensorManager.getRotationMatrix(rotationMatrix, null, accelerometerData, magnetometerData)) {
            SensorManager.getOrientation(rotationMatrix, orientation)

            val magneticHeading = Math.toDegrees(orientation[0].toDouble()).toFloat()
            val normalizedHeading = if (magneticHeading < 0) magneticHeading + 360 else magneticHeading

            // Apply complementary filter if we have gyroscope data.
            // The dt ceiling is what makes a RESUME safe: after a pause the
            // previous sample can be minutes old, and integrating the gyro
            // rate over that gap throws the filtered angle wildly off — from
            // which it recovers only 2% per sample, so the compass reads wrong
            // (or wanders) for many seconds. A gap that large is a restart,
            // not a measurement: fall through and re-seed from the
            // magnetometer instead.
            val gapMs = currentTime - lastComplementaryUpdate
            if (hasGyroscope && lastComplementaryUpdate > 0 && gapMs <= MAX_FILTER_GAP_MS) {
                val dt = gapMs / 1000f
                val gyroRate = Math.toDegrees(gyroscopeData[2].toDouble()).toFloat() // Z-axis rotation

                // Complementary filter: 98% gyro, 2% magnetometer
                val oldAngle = complementaryAngle
                complementaryAngle = 0.98f * (complementaryAngle + gyroRate * dt) + 0.02f * normalizedHeading
                complementaryAngle = (complementaryAngle + 360) % 360

                if (Math.random() < 0.02) {
                    Log.v(TAG, "  Complementary filter:")
                    Log.v(TAG, "  - Gyro rate: ${gyroRate.format(1)}°/s")
                    Log.v(TAG, "  - dt: ${(dt * 1000).format(1)}ms")
                    Log.v(TAG, "  - Old angle: ${oldAngle.format(1)}°")
                    Log.v(TAG, "  - Mag angle: ${normalizedHeading.format(1)}°")
                    Log.v(TAG, "  - New angle: ${complementaryAngle.format(1)}°")
                }
            } else {
                complementaryAngle = normalizedHeading
                Log.v(TAG, "  Complementary filter: Using magnetometer only (no gyro history)")
            }

            lastComplementaryUpdate = currentTime
            lastUpdateTime = currentTime

            val declination = getMagneticDeclination()
            val trueHeading = (complementaryAngle + declination + 360) % 360

            val pitch = Math.toDegrees(orientation[1].toDouble()).toFloat()
            val roll = Math.toDegrees(orientation[2].toDouble()).toFloat()

            sendSensorData(
                magneticHeading = complementaryAngle,
                trueHeading = trueHeading,
                accuracyLevel = magnetometerCalibrationStatus,
                pitch = pitch,
                roll = roll,
                source = "Complementary_Filter"
            )
        }
    }

    private fun getMagneticDeclination(): Float {
        lastLocation?.let { loc ->
            val geoField = GeomagneticField(
                loc.latitude.toFloat(),
                loc.longitude.toFloat(),
                loc.altitude.toFloat(),
                System.currentTimeMillis()
            )
            return geoField.declination
        }
        return 0f
    }


    /**
     * Apply EMA smoothing to a value, handling circular angles properly for headings
     */
    private fun applySmoothingEMA(newValue: Float, smoothedValue: Float?, isAngle: Boolean = false): Float {
    	//return newValue

        return if (smoothedValue == null) {
            newValue
        } else if (isAngle) {
            // Handle circular nature of angles (0-360 degrees)
            val diff = angleDifference(newValue, smoothedValue)
            val smoothedDiff = EMA_ALPHA * diff
            normalizeAngle(smoothedValue + smoothedDiff)
        } else {
            // Regular EMA for non-angular values
            smoothedValue + EMA_ALPHA * (newValue - smoothedValue)
        }
    }

    /**
     * Calculate the shortest angular difference between two angles
     */
    private fun angleDifference(angle1: Float, angle2: Float): Float {
        var diff = angle1 - angle2
        while (diff > 180f) diff -= 360f
        while (diff < -180f) diff += 360f
        return diff
    }

    /**
     * Normalize angle to 0-360 range
     */
    private fun normalizeAngle(angle: Float): Float {
        var normalized = angle % 360f
        if (normalized < 0f) normalized += 360f
        return normalized
    }

    /**
     * Check if sensor values have changed significantly enough to warrant an update
     */
    private fun hasSignificantChange(
        magneticHeading: Float, trueHeading: Float, accuracy: Int,
        pitch: Float, roll: Float
    ): Boolean {
        val headingChanged = lastSentMagneticHeading?.let {
            abs(angleDifference(magneticHeading, it)) >= HEADING_THRESHOLD
        } ?: true

        val trueHeadingChanged = lastSentTrueHeading?.let {
            abs(angleDifference(trueHeading, it)) >= HEADING_THRESHOLD
        } ?: true

        val pitchChanged = lastSentPitch?.let {
            abs(pitch - it) >= PITCH_THRESHOLD
        } ?: true

        val rollChanged = lastSentRoll?.let {
            abs(roll - it) >= ROLL_THRESHOLD
        } ?: true

        val accuracyChanged = lastSentAccuracy?.let {
            abs(accuracy - it) >= ACCURACY_THRESHOLD
        } ?: true

        return headingChanged || trueHeadingChanged || pitchChanged || rollChanged || accuracyChanged
    }

    private fun sendSensorData(
        magneticHeading: Float,
        trueHeading: Float,
        accuracyLevel: Int,
        pitch: Float,
        roll: Float,
        source: String,
        /**
         * The emitting sensor's own rating of this sample
         * (`SensorEvent.accuracy`). -1 from the hand-rolled filters, which
         * compose several raw sensors and have no single rating to pass on.
         */
        fusedSensorAccuracy: Int = -1,
        /**
         * Whether this sample may reach [onSensorUpdate]. False means the per-mode rate
         * limit held it back — [onRawSample] still sees it. Defaults true so the paths
         * that have not been restructured (Madgwick, complementary) behave as before.
         */
        publish: Boolean = true,
        /**
         * How the angles were arrived at, for the diagnostic fields on
         * [OrientationSensorData] — null from every mode that computes no rotation
         * matrix, which is both hand-rolled filters.
         */
        pose: CameraPose? = null,
        /** The HAL's own output, `SensorEvent.values` of the rotation vector. */
        rotationVector: FloatArray? = null,
        /** Whether the 180° branch fix and the azimuth mirror fired on this sample. */
        branchCorrected: Boolean = false,
        azimuthMirrored: Boolean = false,
    ) {
        val startTime = System.currentTimeMillis()
        //Log.v(TAG, "TIMING 🕐 sendSensorData START: ${startTime} from $source")
        // Apply EMA smoothing
        smoothedMagneticHeading = applySmoothingEMA(magneticHeading, smoothedMagneticHeading, isAngle = true)
        smoothedTrueHeading = applySmoothingEMA(trueHeading, smoothedTrueHeading, isAngle = true)
        smoothedPitch = applySmoothingEMA(pitch, smoothedPitch, isAngle = false)
        smoothedRoll = applySmoothingEMA(roll, smoothedRoll, isAngle = false)

        // Use smoothed values
        val finalMagneticHeading = smoothedMagneticHeading!!
        val finalTrueHeading = smoothedTrueHeading!!
        val finalPitch = smoothedPitch!!
        val finalRoll = smoothedRoll!!
		val finalAccuracy = accuracyLevel

        // The sample, built BEFORE the gates so the unthrottled tap can see every one of
        // them. Nothing below may mutate it.
        val sample = OrientationSensorData(
            magneticHeading = finalMagneticHeading,
            trueHeading = finalTrueHeading,
            accuracyLevel = accuracyLevel,
            fusedSensorAccuracy = fusedSensorAccuracy,
            pitch = finalPitch,
            roll = finalRoll,
            timestamp = System.currentTimeMillis(),
            elapsedRealtimeNanos = android.os.SystemClock.elapsedRealtimeNanos(),
            source = "android",
            // Was unconditionally "(EMA smoothed)", which EMA_ALPHA = 1 makes a false
            // claim — that path is a pass-through. Derived from the constant instead, so
            // the label cannot drift from the filter again.
            detail = if (EMA_ALPHA < 1f) "$source (EMA $EMA_ALPHA)" else "$source (unsmoothed)",
            // Only the rotation-vector path fills these; see the field docs. The
            // `toList` is not cosmetic: `SensorEvent.values` is one array the HAL
            // overwrites in place, so keeping a reference would hand every stored sample
            // the LATEST reading. Copy here, inside the synchronous call.
            rotationVector = rotationVector?.toList(),
            matrixDeterminant = pose?.determinant,
            bearingReference = pose?.bearingReference,
            bearingConditioning = pose?.horizontalLength,
            cameraBearingDeg = pose?.bearingDeg,
            deviceBearingDeg = pose?.deviceBearingDeg,
            branchCorrected = pose?.let { branchCorrected },
            azimuthMirrored = pose?.let { azimuthMirrored },
            // Not gated on `pose`: the class is a fact about how the phone is held,
            // measured whatever the fusion mode, and it is recorded precisely because it
            // cannot be recomputed from any sensor series afterwards.
            deviceRotationDeg = DeviceOrientation.toDegrees(deviceOrientation),
            // The matrix's own answer for the two axes gravity now provides, so its
            // faults stay visible after it stopped being the published source.
            matrixPitchDeg = pose?.pitchDeg,
            matrixRollDeg = pose?.imageRollDeg,
            // Whether the compass can be trusted at this spot at all. Computed here
            // because this is where the accelerometer and the magnetometer are both
            // already in hand, and gated on the magnetometer having reported: an
            // all-zero vector would read as a 0 µT field rather than as no reading.
            fieldMagnitudeUt = if (hasMagnetometer) {
                fieldMagnitudeUt(magnetometerData[0], magnetometerData[1], magnetometerData[2])
            } else {
                null
            },
            fieldDipDeg = if (hasMagnetometer) {
                fieldDipDeg(
                    accelerometerData[0], accelerometerData[1], accelerometerData[2],
                    magnetometerData[0], magnetometerData[1], magnetometerData[2],
                )
            } else {
                null
            },
        )
        // Every sample, whatever the cap and the gate decide below.
        onRawSample?.invoke(sample)

        // The per-mode rate limit, for the published stream only — see the `publish`
        // parameter and handleRotationVector.
        if (!publish) return

        // Check if changes are significant enough to warrant an update
        if (!hasSignificantChange(finalMagneticHeading, finalTrueHeading, 0, finalPitch, finalRoll)) {
            //val suppressTime = System.currentTimeMillis()
            //Log.v(TAG, "TIMING 🔇 sendSensorData SUPPRESSED: ${suppressTime} (${suppressTime - startTime}ms) - changes below threshold")
            return
        }

        // Update last sent values
        lastSentMagneticHeading = finalMagneticHeading
        lastSentTrueHeading = finalTrueHeading
        lastSentPitch = finalPitch
        lastSentRoll = finalRoll
        lastSentAccuracy = finalAccuracy

        // Log smoothing effect occasionally
        if (false) {
            Log.w(TAG, "🔧 Smoothing applied:")
            Log.w(TAG, "  Raw values: mag=${magneticHeading.format(1)}°, true=${trueHeading.format(1)}°, pitch=${pitch.format(1)}°, roll=${roll.format(1)}°")
            Log.w(TAG, "  Smoothed:   mag=${finalMagneticHeading.format(1)}°, true=${finalTrueHeading.format(1)}°, pitch=${finalPitch.format(1)}°, roll=${finalRoll.format(1)}°")
            Log.w(TAG, "  EMA_ALPHA=${EMA_ALPHA}, thresholds: heading=${HEADING_THRESHOLD}°, pitch=${PITCH_THRESHOLD}°, roll=${ROLL_THRESHOLD}°")
        }

        val data = sample

        /*val sendTime = System.currentTimeMillis()
        Log.v(TAG, "TIMING 📡 sendSensorData SENDING: ${sendTime} (${sendTime - startTime}ms) bearing=${finalMagneticHeading.format(1)}°")
        */

        onSensorUpdate(data)


        /*val endTime = System.currentTimeMillis()
        Log.v(TAG, "TIMING ✅ sendSensorData COMPLETE: ${endTime} (total: ${endTime - startTime}ms, send: ${endTime - sendTime}ms)")*/
    }
}
