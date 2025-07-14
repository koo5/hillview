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
import kotlin.math.abs

data class SensorData(
    val magneticHeading: Float,
    val trueHeading: Float,
    val headingAccuracy: Float,
    val pitch: Float,
    val roll: Float,
    val timestamp: Long
)

class SensorService(
    private val context: Context,
    private val onSensorUpdate: (SensorData) -> Unit
) : SensorEventListener {
    companion object {
        private const val TAG = "SensorService"
        private const val UPDATE_RATE_MS = 100 // Update every 100ms
    }

    private val sensorManager: SensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val locationManager: LocationManager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
    
    private var rotationVectorSensor: Sensor? = null
    private var magneticSensor: Sensor? = null
    private var accelerometerSensor: Sensor? = null
    
    private var isRunning = false
    
    private var lastUpdateTime = 0L
    private var lastLocation: Location? = null
    
    // Rotation matrix and orientation values
    private val rotationMatrix = FloatArray(9)
    private val inclinationMatrix = FloatArray(9)
    private val orientation = FloatArray(3)
    
    // For fallback to magnetic + accelerometer
    private var gravity = FloatArray(3)
    private var geomagnetic = FloatArray(3)
    private var hasGravity = false
    private var hasGeomagnetic = false
    
    init {
        // Get sensors
        rotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        
        // Fallback sensors if rotation vector not available
        if (rotationVectorSensor == null) {
            magneticSensor = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
            accelerometerSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        }
        
        // Try to get last known location for magnetic declination
        try {
            lastLocation = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                ?: locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
        } catch (e: SecurityException) {
            Log.w(TAG, "Location permission not granted for magnetic declination")
        }
    }
    
    fun startSensor() {
        Log.d(TAG, "Starting sensor service")
        
        if (isRunning) {
            Log.w(TAG, "Sensor already running")
            return
        }
        
        // Register for sensor updates
        rotationVectorSensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
            isRunning = true
            Log.i(TAG, "✅ Registered for TYPE_ROTATION_VECTOR sensor")
        } ?: run {
            // Fallback to magnetic + accelerometer
            magneticSensor?.let { mag ->
                accelerometerSensor?.let { acc ->
                    sensorManager.registerListener(this, mag, SensorManager.SENSOR_DELAY_UI)
                    sensorManager.registerListener(this, acc, SensorManager.SENSOR_DELAY_UI)
                    isRunning = true
                    Log.w(TAG, "⚠️ Falling back to TYPE_MAGNETIC_FIELD + TYPE_ACCELEROMETER sensors")
                }
            }
        }
        
        if (!isRunning) {
            Log.e(TAG, "No orientation sensors available")
        }
    }
    
    fun stopSensor() {
        Log.d(TAG, "Stopping sensor service")
        if (isRunning) {
            sensorManager.unregisterListener(this)
            isRunning = false
        }
    }
    
    fun updateLocation(latitude: Double, longitude: Double) {
        // Update location for better magnetic declination calculation
        lastLocation = Location(LocationManager.GPS_PROVIDER).apply {
            this.latitude = latitude
            this.longitude = longitude
        }
        Log.d(TAG, "Updated location: $latitude, $longitude")
    }
    
    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_ROTATION_VECTOR -> {
                Log.v(TAG, "📡 Received TYPE_ROTATION_VECTOR data")
                handleRotationVector(event)
            }
            Sensor.TYPE_ACCELEROMETER -> {
                gravity = event.values.clone()
                hasGravity = true
                if (hasGeomagnetic) {
                    Log.v(TAG, "📡 Using TYPE_ACCELEROMETER + TYPE_MAGNETIC_FIELD fallback")
                    calculateOrientation()
                }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                geomagnetic = event.values.clone()
                hasGeomagnetic = true
                if (hasGravity) {
                    calculateOrientation()
                }
            }
        }
    }
    
    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {
        Log.d(TAG, "Sensor accuracy changed: ${sensor.name} = $accuracy")
    }
    
    private fun handleRotationVector(event: SensorEvent) {
        // Rate limiting
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastUpdateTime < UPDATE_RATE_MS) {
            return
        }
        lastUpdateTime = currentTime
        
        Log.d(TAG, "🔵 TYPE_ROTATION_VECTOR raw values: ${event.values.contentToString()}")
        
        // Get rotation matrix from rotation vector
        SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)
        
        // Get orientation (azimuth, pitch, roll)
        SensorManager.getOrientation(rotationMatrix, orientation)
        
        // Convert radians to degrees
        val azimuthRad = orientation[0]
        val azimuthDeg = Math.toDegrees(azimuthRad.toDouble()).toFloat()
        
        Log.d(TAG, "🔵 Orientation values: azimuth=$azimuthRad rad (${azimuthDeg}°), pitch=${orientation[1]}, roll=${orientation[2]}")
        
        // Normalize to 0-360
        var heading = if (azimuthDeg < 0) azimuthDeg + 360 else azimuthDeg
        
        // Apply magnetic declination if available
        val declination = getMagneticDeclination()
        val trueHeading = (heading + declination + 360) % 360
        
        // Calculate device tilt (pitch and roll)
        val pitch = Math.toDegrees(orientation[1].toDouble()).toFloat()
        val roll = Math.toDegrees(orientation[2].toDouble()).toFloat()
        
        Log.d(TAG, "🔵 Sending bearing data: magnetic=$heading°, true=$trueHeading°, declination=$declination°")
        
        // Send data callback
        sendSensorData(
            magneticHeading = heading,
            trueHeading = trueHeading,
            accuracy = getAccuracyEstimate(pitch, roll),
            pitch = pitch,
            roll = roll
        )
    }
    
    private fun calculateOrientation() {
        // Fallback calculation using accelerometer + magnetometer
        if (SensorManager.getRotationMatrix(rotationMatrix, inclinationMatrix, gravity, geomagnetic)) {
            SensorManager.getOrientation(rotationMatrix, orientation)
            
            val azimuthRad = orientation[0]
            val azimuthDeg = Math.toDegrees(azimuthRad.toDouble()).toFloat()
            
            var heading = if (azimuthDeg < 0) azimuthDeg + 360 else azimuthDeg
            
            val declination = getMagneticDeclination()
            val trueHeading = (heading + declination + 360) % 360
            
            val pitch = Math.toDegrees(orientation[1].toDouble()).toFloat()
            val roll = Math.toDegrees(orientation[2].toDouble()).toFloat()
            
            sendSensorData(
                magneticHeading = heading,
                trueHeading = trueHeading,
                accuracy = getAccuracyEstimate(pitch, roll) + 5, // Less accurate than rotation vector
                pitch = pitch,
                roll = roll
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
    
    private fun getAccuracyEstimate(pitch: Float, roll: Float): Float {
        // Estimate accuracy based on device orientation
        // More tilt = less accurate compass reading
        val tilt = abs(pitch) + abs(roll)
        return when {
            tilt < 30 -> 3f  // Very accurate when nearly flat
            tilt < 60 -> 5f  // Good accuracy
            tilt < 90 -> 10f // Moderate accuracy
            else -> 15f      // Lower accuracy when highly tilted
        }
    }
    
    private fun sendSensorData(
        magneticHeading: Float,
        trueHeading: Float,
        accuracy: Float,
        pitch: Float,
        roll: Float
    ) {
        val data = SensorData(
            magneticHeading = magneticHeading,
            trueHeading = trueHeading,
            headingAccuracy = accuracy,
            pitch = pitch,
            roll = roll,
            timestamp = System.currentTimeMillis()
        )
        
        onSensorUpdate(data)
    }
}