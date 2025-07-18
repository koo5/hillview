package io.github.koo5.hillview.plugin

import android.app.Activity
import android.util.Log
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import app.tauri.plugin.Invoke

@InvokeArg
class PingArgs {
  var value: String? = null
}

@InvokeArg
class LocationUpdateArgs {
  var latitude: Double = 0.0
  var longitude: Double = 0.0
}

@InvokeArg
class SensorModeArgs {
  var mode: Int? = null
}

@TauriPlugin
class ExamplePlugin(private val activity: Activity): Plugin(activity) {
    companion object {
        private const val TAG = "HillviewPlugin"
        private var pluginInstance: ExamplePlugin? = null
    }
    
    private var sensorService: EnhancedSensorService? = null
    private var preciseLocationService: PreciseLocationService? = null
    
    init {
        pluginInstance = this
    }
    
    @Command
    fun startSensor(invoke: Invoke) {
        val mode = try {
            val args = invoke.parseArgs(SensorModeArgs::class.java)
            if (args != null) {
                Log.d(TAG, "🔄 Successfully parsed args with mode=${args.mode}")
                args.mode ?: EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
            } else {
                Log.d(TAG, "🔄 Args parsed as null, using default mode")
                EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
            }
        } catch (e: Exception) {
            Log.e(TAG, "🔄 Failed to parse args, using default mode. Error: ${e.message}")
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR
        }
        
        Log.d(TAG, "🔄 Starting enhanced sensor service with mode: $mode (${when(mode) {
            EnhancedSensorService.MODE_ROTATION_VECTOR -> "ROTATION_VECTOR"
            EnhancedSensorService.MODE_GAME_ROTATION_VECTOR -> "GAME_ROTATION_VECTOR"
            EnhancedSensorService.MODE_MADGWICK_AHRS -> "MADGWICK_AHRS"
            EnhancedSensorService.MODE_COMPLEMENTARY_FILTER -> "COMPLEMENTARY_FILTER"
            EnhancedSensorService.MODE_UPRIGHT_ROTATION_VECTOR -> "UPRIGHT_ROTATION_VECTOR"
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
                data.put("source", sensorData.source)
                
                //Log.v(TAG, "🔍 Emitting sensor data event: magnetic=${sensorData.magneticHeading}, source=${sensorData.source}")
                
                // Trigger the sensor-data event as per Tauri plugin documentation
                try {
                    // Use just the event name (without plugin: prefix) for plugin events
                    trigger("sensor-data", data)
                    //Log.v(TAG, "🔍 Emitted sensor data event: source=${sensorData.source}, magnetic=${sensorData.magneticHeading}")

                } catch (e: Exception) {
                    Log.e(TAG, "🔍 Error triggering event: ${e.message}", e)
                }
            }
        } else {
            Log.d(TAG, "🔍 SensorService already exists")
        }
        
        Log.d(TAG, "🔄 Calling sensorService.startSensor(mode=$mode)")
        sensorService?.startSensor(mode)
        
        // Also start precise location service for better GPS accuracy
        if (preciseLocationService == null) {
            Log.d(TAG, "📍 Initializing PreciseLocationService alongside sensor")
            initializePreciseLocationService()
        }
        
        Log.d(TAG, "🔄 startSensor command completed")
        invoke.resolve()
    }
    
    @Command
    fun stopSensor(invoke: Invoke) {
        Log.d(TAG, "Stopping sensor service")
        sensorService?.stopSensor()
        
        // Also stop precise location service
        Log.d(TAG, "📍 Stopping precise location service")
        preciseLocationService?.stopLocationUpdates()
        
        invoke.resolve()
    }
    
    @Command
    fun updateSensorLocation(invoke: Invoke) {
        val args = invoke.parseArgs(LocationUpdateArgs::class.java)
        Log.d(TAG, "📍 Updating sensor location: ${args.latitude}, ${args.longitude}")
        
        // Update sensor service for magnetic declination
        sensorService?.updateLocation(args.latitude, args.longitude)
        
        // If we're not using Fused Location, this might be called from JS geolocation
        // Start precise location service if not already running
        if (preciseLocationService == null) {
            Log.d(TAG, "📍 Creating PreciseLocationService as backup")
            initializePreciseLocationService()
        }
        
        invoke.resolve()
    }
    
    private fun initializePreciseLocationService() {
        preciseLocationService = PreciseLocationService(activity) { locationData ->
            // Update sensor service with precise location for magnetic declination
            sensorService?.updateLocation(locationData.latitude, locationData.longitude)
            
            // Emit location update event that matches the existing GeolocationPosition interface
            val data = JSObject()
            
            // Create coords object to match GeolocationPosition interface
            val coords = JSObject()
            coords.put("latitude", locationData.latitude)
            coords.put("longitude", locationData.longitude)
            coords.put("accuracy", locationData.accuracy)
            coords.put("altitude", locationData.altitude)
            coords.put("altitudeAccuracy", locationData.altitudeAccuracy)
            coords.put("heading", locationData.bearing)
            coords.put("speed", locationData.speed)
            
            data.put("coords", coords)
            data.put("timestamp", locationData.timestamp)
            
            // Add extra precision data
            data.put("provider", locationData.provider)
            data.put("bearingAccuracy", locationData.bearingAccuracy)
            data.put("speedAccuracy", locationData.speedAccuracy)
            
            Log.v(TAG, "📍 Emitting location update: lat=${locationData.latitude}, lng=${locationData.longitude}, accuracy=${locationData.accuracy}m")
            
            try {
                // Use the same event name as the geolocation plugin would use
                trigger("location-update", data)
            } catch (e: Exception) {
                Log.e(TAG, "📍 Error triggering location event: ${e.message}", e)
            }
        }
        
        // Start location updates automatically
        preciseLocationService?.startLocationUpdates()
    }
}
