package cz.hillview.plugin

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.GeomagneticField
import android.location.Location
import android.location.LocationManager
import android.os.Process
import android.util.Log
import android.view.OrientationEventListener
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
    private val onSensorUpdate: (OrientationSensorData) -> Unit,
) : SensorEventListener {
    companion object {
        private const val TAG = "🢄Sensors"
        private const val UPDATE_RATE_MS = 10 // Higher frequency for better fusion
        private const val SENSOR_DELAY = 1000*30//SensorManager.SENSOR_DELAY_GAME // Faster updates

        // Smoothing and filtering parameters
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
    private var originalThreadPriority: Int? = null

    // Sensor data buffers
    private var accelerometerData = FloatArray(3)
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

    // Device orientation tracking
    private var deviceOrientation = DeviceOrientation.PORTRAIT

    private val orientationEventListener = object : OrientationEventListener(context) {
        override fun onOrientationChanged(orientation: Int) {
			//Log.d(TAG, "📱 onOrientationChanged: $orientation")

            val newOrientation = DeviceOrientation.fromDegrees(orientation)

            if (newOrientation != deviceOrientation) {
                Log.d(TAG, "📱 Device orientation changed: $deviceOrientation → $newOrientation")
                deviceOrientation = newOrientation
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
        initializeLifecycleObserver()
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

    private fun startSensorInternal(mode: Int = MODE_UPRIGHT_ROTATION_VECTOR) {
        if (isRunning) {
            Log.w(TAG, "🔀 Sensor already running in mode: ${MODE_NAMES[currentMode]}, switching to ${MODE_NAMES[mode]}")
            stopSensorInternal()
        }

        // Boost thread priority for sensor processing to prevent starvation during photo capture
        try {
            if (originalThreadPriority == null) {
                originalThreadPriority = Process.getThreadPriority(Process.myTid())
            }
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_DISPLAY)
            Log.i(TAG, "🚀 SENSOR THREAD PRIORITY: boosted from ${originalThreadPriority} to ${Process.THREAD_PRIORITY_URGENT_DISPLAY}")
        } catch (e: Exception) {
            Log.w(TAG, "⚠️ Failed to set sensor thread priority: ${e.message}")
        }

		Log.i(TAG, "🔍📡 TYPE_HEADING and TYPE_POSE_6DOF sensors if available: headingSensor: ${headingSensor != null}, poseSensor: ${poseSensor != null}")
        /*headingSensor?.let { sensorManager.registerListener(this, it, SENSOR_DELAY) }
        poseSensor?.let { sensorManager.registerListener(this, it, SENSOR_DELAY) }*/
		//isRunning = true

        currentMode = mode
        Log.i(TAG, "🔍🚀 Starting enhanced sensor service")
        Log.i(TAG, "🔍📋 Mode: ${MODE_NAMES[mode]} (code: $mode)")


        when (mode) {
            MODE_ROTATION_VECTOR -> {
                rotationVectorSensor?.let {
                    Log.d(TAG, "🔍📡 Registering TYPE_ROTATION_VECTOR sensor")
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                    isRunning = true
                    Log.i(TAG, "✅ Started TYPE_ROTATION_VECTOR successfully")
                } ?: Log.e(TAG, "❌ TYPE_ROTATION_VECTOR sensor not available")
            }
            MODE_GAME_ROTATION_VECTOR -> {
                // Try game rotation vector first (better for upright phone)
                gameRotationVectorSensor?.let {
                    Log.d(TAG, "🔍📡 Registering TYPE_GAME_ROTATION_VECTOR sensor")
                    Log.d(TAG, "🔍📱 This mode is optimized for upright phone usage")
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
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
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                    sensorsRegistered++
                    Log.d(TAG, "  ✓ Registered ACCELEROMETER")
                } ?: Log.w(TAG, "  ❌ ACCELEROMETER not available")

                gyroscopeSensor?.let {
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                    sensorsRegistered++
                    Log.d(TAG, "  ✓ Registered GYROSCOPE")
                } ?: Log.w(TAG, "  ❌ GYROSCOPE not available")

                magnetometerSensor?.let {
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
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
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                }
                magnetometerSensor?.let {
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                }
                gyroscopeSensor?.let {
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                }
                isRunning = true
                Log.i(TAG, "Started complementary filter")
            }
            MODE_UPRIGHT_ROTATION_VECTOR -> {
                // Use rotation vector but optimized for upright phone position
                magnetometerSensor?.let {
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                    Log.d(TAG, "  ✓ Registered MAGNETOMETER")
                } ?: Log.w(TAG, "  ❌ MAGNETOMETER not available")

                rotationVectorSensor?.let {
                    Log.d(TAG, "🔄 Registering TYPE_ROTATION_VECTOR sensor for UPRIGHT mode")
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
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
            Log.i(TAG, "  - Sensor delay: SENSOR_DELAY_GAME")
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

    override fun onSensorChanged(event: SensorEvent) {

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
        // Rate limiting based on current mode
        val currentTime = System.currentTimeMillis()
        val rateLimit = MODE_RATE_LIMITS[currentMode] ?: UPDATE_RATE_MS

        if (currentTime - lastUpdateTime < rateLimit) {
            return
        }
        lastUpdateTime = currentTime

        //Log.v(TAG, "🔍📊 Processing $source data")

        // Get rotation matrix
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
		val prefs = context.getSharedPreferences("landscape_compass_armor22_workaround", Context.MODE_PRIVATE)
        val workaround1 = prefs.getBoolean("enabled", false)
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
        val trueHeading = (heading + declination + 360) % 360

        // Log every 20th update to avoid spam
        /*if (Math.random() < 0.05) {
            Log.d(TAG, "🔍🧭 $source bearing:")
            Log.d(TAG, "  - Magnetic: ${heading.format(1)}°")
            Log.d(TAG, "  - True: ${trueHeading.format(1)}°")*/
            Log.d(TAG, "  - Accuracy level: ${event.accuracy}")
            /*
            Log.d(TAG, "  - Pitch: ${pitch.format(1)}°, Roll: ${roll.format(1)}°")
        }*/

        // Include mode information in source
        val sourceWithMode = when (currentMode) {
            MODE_UPRIGHT_ROTATION_VECTOR -> "$source (UPRIGHT MODE)"
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
            source = sourceWithMode
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



    private fun updateMadgwick() {
        if (!hasAccelerometer || !hasGyroscope || !hasMagnetometer) {
            return
        }

        // Rate limiting
        val currentTime = System.currentTimeMillis()
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

        val currentTime = System.currentTimeMillis()
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

            // Apply complementary filter if we have gyroscope data
            if (hasGyroscope && lastComplementaryUpdate > 0) {
                val dt = (currentTime - lastComplementaryUpdate) / 1000f
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
        source: String
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

        val data = OrientationSensorData(
            magneticHeading = finalMagneticHeading,
            trueHeading = finalTrueHeading,
            accuracyLevel = accuracyLevel,
            pitch = finalPitch,
            roll = finalRoll,
            timestamp = System.currentTimeMillis(),
            source = "android $source (EMA smoothed)"
        )

        /*val sendTime = System.currentTimeMillis()
        Log.v(TAG, "TIMING 📡 sendSensorData SENDING: ${sendTime} (${sendTime - startTime}ms) bearing=${finalMagneticHeading.format(1)}°")
        */

        onSensorUpdate(data)


        /*val endTime = System.currentTimeMillis()
        Log.v(TAG, "TIMING ✅ sendSensorData COMPLETE: ${endTime} (total: ${endTime - startTime}ms, send: ${endTime - sendTime}ms)")*/
    }
}
