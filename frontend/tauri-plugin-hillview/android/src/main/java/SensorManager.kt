package cz.hillview.plugin

import android.app.Activity
import android.util.Log
import app.tauri.plugin.JSObject

class SensorManager(private val activity: Activity, private val permissionManager: PermissionManager) {
    companion object {
        private const val TAG = "SensorManager"
    }

    private var sensorService: EnhancedSensorService? = null
    private var preciseLocationService: PreciseLocationService? = null

    fun startSensor(mode: Int = EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR) {
        Log.d(TAG, "🔄 Starting sensor service with mode: $mode (${when(mode) {
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR -> "UPRIGHT_ROTATION_VECTOR"
            EnhancedSensorService.MODE_ROTATION_VECTOR -> "ROTATION_VECTOR"
            EnhancedSensorService.MODE_GAME_ROTATION_VECTOR -> "GAME_ROTATION_VECTOR"
            EnhancedSensorService.MODE_MADGWICK_AHRS -> "MADGWICK_AHRS"
            EnhancedSensorService.MODE_COMPLEMENTARY_FILTER -> "COMPLEMENTARY_FILTER"
            else -> "UNKNOWN"
        }})")

        if (sensorService == null) {
            Log.d(TAG, "🔍 Creating new EnhancedSensorService instance")
            sensorService = EnhancedSensorService(activity) { sensorData ->
                // Emit sensor data event
                val data = JSObject()
                data.put("magneticHeading", sensorData.magneticHeading)
                data.put("trueHeading", sensorData.trueHeading)
                data.put("headingAccuracy", sensorData.headingAccuracy)
                data.put("pitch", sensorData.pitch)
                data.put("roll", sensorData.roll)
                data.put("timestamp", sensorData.timestamp)

                // Note: Event emission would be handled by the main plugin
                Log.v(TAG, "Sensor data: heading=${String.format("%.1f", sensorData.magneticHeading)}° pitch=${String.format("%.1f", sensorData.pitch)}° roll=${String.format("%.1f", sensorData.roll)}°")
            }
        }

        // Start the sensor service
        sensorService?.startSensor(mode)

        // Also start precise location service for better GPS accuracy
        if (preciseLocationService == null) {
            Log.d(TAG, "📍 Initializing PreciseLocationService alongside sensor")
            initializePreciseLocationService()
        }

        Log.d(TAG, "🔄 startSensor command completed")
    }

    fun stopSensor() {
        Log.d(TAG, "🔄 Stopping sensor service")
        sensorService?.stopSensor()
        preciseLocationService?.stopLocationUpdates()
    }

    fun startPreciseLocationListener() {
        Log.i(TAG, "📍 Starting precise location listener")
        if (preciseLocationService == null) {
            initializePreciseLocationService()
        }
        preciseLocationService?.startLocationUpdates()
    }

    fun stopPreciseLocationListener() {
        Log.i(TAG, "📍 Stopping precise location listener")
        preciseLocationService?.stopLocationUpdates()
    }

    private fun initializePreciseLocationService() {
        if (preciseLocationService == null) {
            Log.d(TAG, "📍 Creating PreciseLocationService instance")
            preciseLocationService = PreciseLocationService(
                activity, 
                permissionManager,
                { locationData ->
                    // Emit location data event
                    val data = JSObject()
                    data.put("latitude", locationData.latitude)
                    data.put("longitude", locationData.longitude)
                    
                    // Note: Event emission would be handled by the main plugin
                    Log.v(TAG, "Location update: ${locationData.latitude}, ${locationData.longitude}")
                }
            )
        }
    }

    fun cleanup() {
        Log.d(TAG, "🧹 Cleaning up sensor services")
        sensorService?.stopSensor()
        preciseLocationService?.stopLocationUpdates()
        sensorService = null
        preciseLocationService = null
    }
}