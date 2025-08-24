package io.github.koo5.hillview.plugin

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.GeomagneticField
import android.location.Location
import android.location.LocationManager
import android.util.Log
import kotlin.math.*

data class SensorData(
    val magneticHeading: Float,  // Compass bearing in degrees from magnetic north (0-360°)
    val trueHeading: Float,       // Compass bearing corrected for magnetic declination
    val headingAccuracy: Float,
    val pitch: Float,
    val roll: Float,
    val timestamp: Long,
    val source: String      // Identifies which sensor provided the data
)

// Extension function for float formatting
private fun Float.format(digits: Int) = "%.${digits}f".format(this)

/**
 * Enhanced sensor service that provides more accurate bearing information
 * when the phone is upright by using multiple sensor fusion techniques.
 */
class EnhancedSensorService(
    private val context: Context,
    private val onSensorUpdate: (SensorData) -> Unit
) : SensorEventListener {
    companion object {
        private const val TAG = "🢄EnhancedSensorService"
        private const val UPDATE_RATE_MS = 10 // Higher frequency for better fusion
        private const val SENSOR_DELAY = SensorManager.SENSOR_DELAY_GAME // Faster updates
        
        // Smoothing and filtering parameters
        private const val EMA_ALPHA = 1f // EMA smoothing factor (0.1-0.3 range, lower = more smoothing)
        private const val HEADING_THRESHOLD = 1.0f // Minimum heading change to trigger update (degrees)
        private const val PITCH_THRESHOLD = 3.0f // Minimum pitch change to trigger update (degrees) 
        private const val ROLL_THRESHOLD = 3.0f // Minimum roll change to trigger update (degrees)
        private const val ACCURACY_THRESHOLD = 1.0f // Minimum accuracy change to trigger update (degrees)
        
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
    
    // Sensor fusion algorithms
    private val madgwickAHRS = MadgwickAHRS(sampleFreq = 50f, beta = 0.1f)
    
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
    private var magnetometerCalibrationStatus = SensorManager.SENSOR_STATUS_ACCURACY_LOW
    
    private var isRunning = false
    private var currentMode = MODE_ROTATION_VECTOR
    private var lastUpdateTime = 0L
    private var lastLocation: Location? = null
    
    // EMA smoothing state
    private var smoothedMagneticHeading: Float? = null
    private var smoothedTrueHeading: Float? = null
    private var smoothedPitch: Float? = null
    private var smoothedRoll: Float? = null
    private var smoothedAccuracy: Float? = null
    private var lastSentMagneticHeading: Float? = null
    private var lastSentTrueHeading: Float? = null
    private var lastSentPitch: Float? = null
    private var lastSentRoll: Float? = null
    private var lastSentAccuracy: Float? = null
    
    // Rotation matrices
    private val rotationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)
    
    init {
        // Initialize sensors
        rotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        gameRotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
        geomagneticRotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR)
        accelerometerSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        gyroscopeSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
        magnetometerSensor = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
        
        // Log available sensors
        Log.i(TAG, "🔍 === ENHANCED SENSOR SERVICE INITIALIZED ===")
        Log.i(TAG, "🔍📱 Available sensors:")
        Log.i(TAG, "  ✓ TYPE_ROTATION_VECTOR: ${rotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GAME_ROTATION_VECTOR: ${gameRotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GEOMAGNETIC_ROTATION_VECTOR: ${geomagneticRotationVectorSensor != null}")
        Log.i(TAG, "  ✓ TYPE_ACCELEROMETER: ${accelerometerSensor != null}")
        Log.i(TAG, "  ✓ TYPE_GYROSCOPE: ${gyroscopeSensor != null}")
        Log.i(TAG, "  ✓ TYPE_MAGNETIC_FIELD: ${magnetometerSensor != null}")
        
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
    }
    
    fun startSensor(mode: Int = MODE_UPRIGHT_ROTATION_VECTOR) {
        if (isRunning) {
            Log.w(TAG, "🔀 Sensor already running in mode: ${MODE_NAMES[currentMode]}, switching to ${MODE_NAMES[mode]}")
            stopSensor()
        }
        
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
                rotationVectorSensor?.let {
                    Log.d(TAG, "🔄 Registering TYPE_ROTATION_VECTOR sensor for UPRIGHT mode")
                    Log.d(TAG, "🔄 Will remap coordinates for portrait orientation")
                    sensorManager.registerListener(this, it, SENSOR_DELAY)
                    isRunning = true
                    Log.i(TAG, "✅ Started UPRIGHT_ROTATION_VECTOR mode successfully")
                } ?: run {
                    Log.e(TAG, "❌ TYPE_ROTATION_VECTOR not available")
                }
            }
        }
        
        if (!isRunning) {
            Log.e(TAG, "❌ Failed to start any sensor mode")
        } else {
            Log.i(TAG, "🔍🎯 Current configuration:")
            Log.i(TAG, "  - Mode: ${MODE_NAMES[currentMode]}")
            Log.i(TAG, "  - Rate limit: ${MODE_RATE_LIMITS[currentMode]}ms (${1000.0/(MODE_RATE_LIMITS[currentMode]?:100)} Hz)")
            Log.i(TAG, "  - Sensor delay: SENSOR_DELAY_GAME")
        }
    }
    
    fun stopSensor() {
        if (isRunning) {
            Log.i(TAG, "🔍🛑 Stopping sensor service (mode: ${MODE_NAMES[currentMode]})")
            sensorManager.unregisterListener(this)
            isRunning = false
            hasAccelerometer = false
            hasGyroscope = false
            hasMagnetometer = false
            
            // Reset smoothing state to avoid stale values on restart
            smoothedMagneticHeading = null
            smoothedTrueHeading = null
            smoothedPitch = null
            smoothedRoll = null
            smoothedAccuracy = null
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
        Log.d(TAG, "📍 Updated location: $latitude, $longitude")
    }
    
    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ROTATION_VECTOR -> {
                //Log.v(TAG, "🔍📡 Received TYPE_ROTATION_VECTOR data")
                val source = if (currentMode == MODE_UPRIGHT_ROTATION_VECTOR) {
                    "TYPE_ROTATION_VECTOR (UPRIGHT)"
                } else {
                    "TYPE_ROTATION_VECTOR"
                }
                handleRotationVector(event, source)
            }
            Sensor.TYPE_GAME_ROTATION_VECTOR -> {
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
            }
        }
    }
    
    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {
        val accuracyStr = when (accuracy) {
            SensorManager.SENSOR_STATUS_ACCURACY_HIGH -> "HIGH"
            SensorManager.SENSOR_STATUS_ACCURACY_MEDIUM -> "MEDIUM"
            SensorManager.SENSOR_STATUS_ACCURACY_LOW -> "LOW"
            SensorManager.SENSOR_STATUS_UNRELIABLE -> "UNRELIABLE"
            else -> "UNKNOWN"
        }
        
        when (sensor.type) {
            Sensor.TYPE_MAGNETIC_FIELD -> {
                magnetometerCalibrationStatus = accuracy
                Log.i(TAG, "🔍🧭 Magnetometer accuracy changed: $accuracyStr ($accuracy)")
                if (accuracy == SensorManager.SENSOR_STATUS_ACCURACY_LOW) {
                    Log.w(TAG, "⚠️ Low magnetometer accuracy - consider calibrating by moving device in figure-8 pattern")
                }
            }
            Sensor.TYPE_ACCELEROMETER -> {
                Log.d(TAG, "🔍📈 Accelerometer accuracy: $accuracyStr")
            }
            Sensor.TYPE_GYROSCOPE -> {
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
        
        // For upright mode, remap coordinate system
        if (currentMode == MODE_UPRIGHT_ROTATION_VECTOR) {
            val remappedRotationMatrix = FloatArray(9)
            // 🔄 Remap X axis to Z axis, Y axis stays Y
            // 🔄 This handles portrait orientation where phone is held upright
            SensorManager.remapCoordinateSystem(
                rotationMatrix,
                SensorManager.AXIS_X,
                SensorManager.AXIS_Z,
                remappedRotationMatrix
            )
            System.arraycopy(remappedRotationMatrix, 0, rotationMatrix, 0, 9)
            //Log.v(TAG, "🔄 Applied coordinate remapping for upright mode")
        }
        
        // Get orientation
        SensorManager.getOrientation(rotationMatrix, orientation)
        
        // Convert to degrees
        val azimuth = Math.toDegrees(orientation[0].toDouble()).toFloat()
        val pitch = Math.toDegrees(orientation[1].toDouble()).toFloat()
        val roll = Math.toDegrees(orientation[2].toDouble()).toFloat()
        
        // Normalize heading
        val heading = if (azimuth < 0) azimuth + 360 else azimuth
        
        // Apply magnetic declination to convert from magnetic north to true north
        val declination = getMagneticDeclination()
        val trueHeading = (heading + declination + 360) % 360
        
        // Calculate accuracy based on sensor type and device orientation
        val accuracy = when (source) {
            "TYPE_GAME_ROTATION_VECTOR" -> getGameRotationAccuracy(pitch, roll)
            "TYPE_GEOMAGNETIC_ROTATION_VECTOR" -> getGeomagneticAccuracy(pitch, roll)
            else -> getStandardAccuracy(pitch, roll)
        }
        
        // Log every 20th update to avoid spam
        /*if (Math.random() < 0.05) {
            Log.d(TAG, "🔍🧭 $source bearing:")
            Log.d(TAG, "  - Magnetic: ${heading.format(1)}°")
            Log.d(TAG, "  - True: ${trueHeading.format(1)}°")
            Log.d(TAG, "  - Accuracy: ±${accuracy.format(1)}°")
            Log.d(TAG, "  - Pitch: ${pitch.format(1)}°, Roll: ${roll.format(1)}°")
        }*/
        
        // Include mode information in source
        val sourceWithMode = when (currentMode) {
            MODE_UPRIGHT_ROTATION_VECTOR -> "$source (UPRIGHT MODE)"
            MODE_MADGWICK_AHRS -> "MADGWICK_AHRS"
            MODE_COMPLEMENTARY_FILTER -> "COMPLEMENTARY_FILTER"
            else -> source
        }
        
        sendSensorData(
            magneticHeading = heading,
            trueHeading = trueHeading,
            headingAccuracy = accuracy,
            pitch = pitch,
            roll = roll,
            source = sourceWithMode
        )
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
            headingAccuracy = getMadgwickAccuracy(pitchDeg, rollDeg),
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
                headingAccuracy = getComplementaryAccuracy(pitch, roll),
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
    
    // Accuracy estimation methods for different sensor types
    private fun getStandardAccuracy(pitch: Float, roll: Float): Float {
        val tilt = abs(pitch) + abs(roll)
        return when {
            tilt < 30 -> 3f
            tilt < 60 -> 5f
            tilt < 90 -> 10f
            else -> 15f
        }
    }
    
    private fun getGameRotationAccuracy(pitch: Float, @Suppress("UNUSED_PARAMETER") roll: Float): Float {
        // Game rotation vector is more accurate when upright
        val uprightness = 90 - abs(pitch)
        return when {
            uprightness > 60 -> 2f  // Very accurate when upright
            uprightness > 30 -> 4f
            uprightness > 0 -> 8f
            else -> 12f
        }
    }
    
    private fun getGeomagneticAccuracy(pitch: Float, roll: Float): Float {
        // Consider magnetometer calibration status
        val baseAccuracy = getStandardAccuracy(pitch, roll)
        return when (magnetometerCalibrationStatus) {
            SensorManager.SENSOR_STATUS_ACCURACY_HIGH -> baseAccuracy
            SensorManager.SENSOR_STATUS_ACCURACY_MEDIUM -> baseAccuracy + 2f
            SensorManager.SENSOR_STATUS_ACCURACY_LOW -> baseAccuracy + 5f
            else -> baseAccuracy + 10f
        }
    }
    
    private fun getMadgwickAccuracy(pitch: Float, @Suppress("UNUSED_PARAMETER") roll: Float): Float {
        // Madgwick typically provides very good accuracy
        return when {
            abs(pitch) < 80 -> 2f  // Excellent accuracy except when nearly vertical
            else -> 5f
        }
    }
    
    private fun getComplementaryAccuracy(@Suppress("UNUSED_PARAMETER") pitch: Float, @Suppress("UNUSED_PARAMETER") roll: Float): Float {
        // Complementary filter accuracy depends on magnetometer calibration
        val baseAccuracy = 3f
        return when (magnetometerCalibrationStatus) {
            SensorManager.SENSOR_STATUS_ACCURACY_HIGH -> baseAccuracy
            SensorManager.SENSOR_STATUS_ACCURACY_MEDIUM -> baseAccuracy + 2f
            else -> baseAccuracy + 4f
        }
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
        magneticHeading: Float, trueHeading: Float, accuracy: Float,
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
        headingAccuracy: Float,
        pitch: Float,
        roll: Float,
        source: String
    ) {
        // Apply EMA smoothing
        smoothedMagneticHeading = applySmoothingEMA(magneticHeading, smoothedMagneticHeading, isAngle = true)
        smoothedTrueHeading = applySmoothingEMA(trueHeading, smoothedTrueHeading, isAngle = true)
        smoothedPitch = applySmoothingEMA(pitch, smoothedPitch, isAngle = false)
        smoothedRoll = applySmoothingEMA(roll, smoothedRoll, isAngle = false)
        smoothedAccuracy = applySmoothingEMA(headingAccuracy, smoothedAccuracy, isAngle = false)
        
        // Use smoothed values
        val finalMagneticHeading = smoothedMagneticHeading!!
        val finalTrueHeading = smoothedTrueHeading!!
        val finalPitch = smoothedPitch!!
        val finalRoll = smoothedRoll!!
        val finalAccuracy = smoothedAccuracy!!
        
        // Check if changes are significant enough to warrant an update
        if (!hasSignificantChange(finalMagneticHeading, finalTrueHeading, finalAccuracy, finalPitch, finalRoll)) {
            // Log suppressed update occasionally
            /*if (Math.random() < 0.01) {
                Log.v(TAG, "🔇 Suppressing update - changes below significance threshold")
                Log.v(TAG, "  Raw: mag=${magneticHeading.format(1)}°, true=${trueHeading.format(1)}°, pitch=${pitch.format(1)}°, roll=${roll.format(1)}°")
                Log.v(TAG, "  Smoothed: mag=${finalMagneticHeading.format(1)}°, true=${finalTrueHeading.format(1)}°, pitch=${finalPitch.format(1)}°, roll=${finalRoll.format(1)}°")
            }*/
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
        
        val data = SensorData(
            magneticHeading = finalMagneticHeading,
            trueHeading = finalTrueHeading,
            headingAccuracy = finalAccuracy,
            pitch = finalPitch,
            roll = finalRoll,
            timestamp = System.currentTimeMillis(),
            source = "$source (EMA smoothed)"
        )
        
        onSensorUpdate(data)
    }
}